"""Find the article -> section structure, annexes, definitions and defined terms."""

import re
from dataclasses import dataclass, field

from app.ingest.parse import find_body_end, find_body_start
from app.text import normalize

# --- data model -----------------------------------------------------------------------

ANNEX_ARTICLE = 0  # article_number used for annexes kept after the signature pages


@dataclass
class Article:
    number: int
    label: str  # as written: "VIII", "10", "ONE"
    title: str
    word: str = "ARTICLE"  # or "SECTION" in agreements that use "Section 1." as the top level


@dataclass
class Section:
    article_number: int
    article_title: str
    number: str  # as written, without "Section": "10.01", "8.2"; or "Annex I"
    title: str
    lines: list[str] = field(default_factory=list)
    defined_terms: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@dataclass
class Definition:
    term: str
    text: str
    section_number: str


@dataclass
class ParsedAgreement:
    deal_id: str
    preamble: str
    articles: list[Article]
    sections: list[Section]  # body sections, then kept annexes (article_number 0)
    definitions: list[Definition]
    term_index: dict[str, str]  # term -> where it is defined, from index tables
    body_start_method: str
    end_marker_found: bool
    dropped_annexes: list[str]  # titles of exhibits left out (forms of other documents)
    trailing_chars: int  # text after the signature block that was not kept
    warnings: list[str]


# --- heading patterns -----------------------------------------------------------------

# Top-level headings. Most agreements use "ARTICLE VIII"; some (Ansys) use "Section 8."
# with sections numbered 8.1, 8.2 below it. The lookahead keeps "Section 8.1" out.
ARTICLE_RE = re.compile(
    r"^(?P<word>ARTICLE|SECTION)\s+(?P<num>[IVXLC]+|\d{1,2}|[A-Z]+)\b(?!\.\d)"
    r"[\s.:\-]*(?P<rest>.*)$",
    re.I,
)
_FIRST_ARTICLE_WORD = re.compile(r"^ARTICLE\s+(?:I|1|ONE)\b", re.I)
SECTION_RE = re.compile(
    r"^(?:(?:Section|Sec\.|§)\s*)?(?P<major>\d{1,2})\.(?P<minor>\d{1,3})\b\.?(?P<rest>.*)$", re.I
)
ANNEX_RE = re.compile(
    r"^(?P<kind>ANNEX|EXHIBIT|SCHEDULE|APPENDIX)\s+(?P<label>[A-Z]{1,3}|\d{1,2})\b"
    r"[\s.:\-–—]*(?P<rest>.*)$",
    re.I,
)
# Annexes worth keeping. Everything else after the signatures is a form of another
# document (charter, bylaws, voting agreement) and is dropped.
KEEP_ANNEX_RE = re.compile(r"definition|condition", re.I)

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
_NUMBER_WORDS = (
    "ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE TEN ELEVEN TWELVE THIRTEEN FOURTEEN FIFTEEN"
)
_WORDS = {word: n for n, word in enumerate(_NUMBER_WORDS.split(" "), start=1)}
# Words that show "ARTICLE V ..." is a cross-reference in a sentence, not a heading.
_REFERENCE_WORDS = {"of", "and", "or", "to", "in", "shall", "hereof", "above", "below", "herein"}

_VERB = r"(?:shall\s+)?(?:means?|includes?|(?:has|have)\s+the\s+meanings?|(?:is|are)\s+defined)\b"
_ALSO = r'(?:\s*,?\s+(?:or|and)\s+"[^"]{1,80}")?'
# List-style definitions at the start of a paragraph, optionally lettered:
#   "Term" means ...     (a) "Term" means ...     "Tax" or "Taxes" means ...
DEFINITION_RE = re.compile(
    rf'^(?:\([a-z0-9]{{1,4}}\)\s+)?"(?P<term>[^"]{{1,80}})"{_ALSO}\s+{_VERB}'
)
# Definitions inside a paragraph: ... the term "Tax" means ... / For purposes of
# this Agreement, "Subsidiary" means ...
INLINE_DEFINITION_RE = re.compile(
    rf'"(?P<term>[A-Z][^"]{{1,80}})"{_ALSO}\s+(?:shall\s+)?(?:means|has\s+the\s+meaning)\b'
)
# Defined in passing: ... (the "End Date") or (each, an "Equity Investor")
INLINE_TERM_RE = re.compile(r'"(?P<term>[A-Z][^"]{1,60})"\s*\)')
# Index tables: a term on one line, where it is defined on the next.
INDEX_REF_RE = re.compile(
    r"^(?:Section\s+)?(?P<ref>\d{1,2}\.\d{1,3}(?:\([a-z0-9]+\))*|Preamble|Recitals?)$", re.I
)
# Section references such as "Section 10.01(b)(i)" or "8.3(b)".
SECTION_REF_RE = re.compile(r"(?P<major>\d{1,2})\.(?P<minor>\d{1,3})(?P<subs>(?:\([a-z0-9]+\))*)")
_SENTENCE_END = re.compile(r"\.\s+(?=[A-Z(\"])")

SectionKey = tuple[int, int, tuple[str, ...]]


def article_number(token: str) -> int | None:
    token = token.upper()
    if token.isdigit():
        return int(token)
    if token in _WORDS:
        return _WORDS[token]
    if not token or any(ch not in _ROMAN for ch in token):
        return None
    total = 0
    for i, ch in enumerate(token):
        value = _ROMAN[ch]
        total += -value if i + 1 < len(token) and _ROMAN[token[i + 1]] > value else value
    return total


def section_key(label: str) -> SectionKey | None:
    """'Section 8.03(b)(i).' -> (8, 3, ('b', 'i')). Zero padding does not matter."""
    match = SECTION_REF_RE.search(label)
    if not match:
        return None
    subs = tuple(re.findall(r"\(([a-z0-9]+)\)", match["subs"]))
    return int(match["major"]), int(match["minor"]), subs


def section_matches(reference: str, retrieved: str) -> bool:
    """True if `retrieved` is the referenced section or contains it.

    Chunks are section-level, references are often subsection-level, so a retrieved
    "2.02" satisfies a reference to "2.02(a)", but "2.02(b)" does not. Annex labels
    ("Annex I") have no numbers and are compared as text.
    """
    ref, got = section_key(reference), section_key(retrieved)
    if ref is None or got is None:
        return (
            ref is None
            and got is None
            and normalize(reference).lower() == normalize(retrieved).lower().rstrip(".")
        )
    return ref[:2] == got[:2] and ref[2][: len(got[2])] == got[2]


# --- helpers --------------------------------------------------------------------------


def _is_upper_text(text: str) -> bool:
    letters = [ch for ch in text if ch.isalpha()]
    return bool(letters) and all(ch.isupper() for ch in letters)


def _split_title(text: str) -> tuple[str, str] | None:
    """'Termination. This Agreement may...' -> ('Termination', 'This Agreement may...')."""
    for match in re.finditer(r"\.(?:\s|$)", text):
        end = match.start()
        if end >= 2 and text[end - 2] == ".":  # abbreviation such as "U.S."
            continue
        title = text[:end].strip()
        if 0 < len(title) <= 120:
            return title, text[match.end() :].strip()
        return None
    return None


def _section_title(rest: str, following: list[str]) -> tuple[str, str, int]:
    """Return (title, body text on the heading line, number of following lines used)."""
    rest = rest.strip().lstrip(".:-— ").strip()
    if rest:
        split = _split_title(rest)
        if split:
            return split[0], split[1], 0
        if len(rest) <= 120:
            return rest, "", 0
        return "", rest, 0

    parts: list[str] = []
    for line in following[:4]:
        if line.startswith("(") or SECTION_RE.match(line) or ARTICLE_RE.match(line):
            break
        if len(line) > 150:
            if not parts:  # title and body share the next line
                split = _split_title(line)
                if split:
                    return split[0], split[1], 1
            break
        parts.append(line)
        if line.endswith("."):
            title = re.sub(r"\s+\.", ".", " ".join(parts)).rstrip(".").strip()
            return title, "", len(parts)
    if parts:  # no closing period: trust only the first short line
        return parts[0].rstrip("."), "", 1
    return "", "", 0


def _article_title(rest: str, following: list[str]) -> tuple[str, int]:
    """Article titles are shown in capitals, but CSS can do that to lowercase source text,
    so the first title line may be in any case. Wrapped continuation lines must be capitals.
    """
    rest = rest.strip(" .:-—")
    if rest:
        return rest.upper(), 0
    parts: list[str] = []
    for line in following[:3]:
        if len(line) > 150 or SECTION_RE.match(line) or ARTICLE_RE.match(line):
            break
        if line.endswith(":") or line.startswith("("):
            break  # an introductory sentence, not a title
        if parts and not _is_upper_text(line):
            break
        parts.append(line)
    return " ".join(parts).upper(), len(parts)


def _is_article_heading(line: str, rest: str) -> bool:
    if len(line) >= 150:
        return False
    rest = rest.strip(" .:-—")
    if not rest:
        return True
    first_word = rest.split()[0].lower()
    return not rest[0].islower() and first_word not in _REFERENCE_WORDS


# --- definitions and term indexes --------------------------------------------------------


def _definitions(section: Section) -> list[Definition]:
    found: list[Definition] = []
    current: Definition | None = None
    for line in section.lines:
        match = DEFINITION_RE.match(line)
        if match:
            current = Definition(match["term"].strip(), line, section.number)
            found.append(current)
            continue
        if current and (line.startswith("(") or line[:1].islower() or line.startswith("provided")):
            current.text += "\n" + line  # (i), (ii) clauses and provisos belong to it
            continue
        current = None
        for inline in INLINE_DEFINITION_RE.finditer(line):
            # Keep just the sentence that does the defining.
            tail = line[inline.start() :]
            stop = _SENTENCE_END.search(tail)
            text = tail[: stop.start() + 1] if stop else tail
            found.append(Definition(inline["term"].strip(), text[:2000], section.number))
    return found


def _index_pair(term_line: str, ref_line: str) -> tuple[str, str] | None:
    match = INDEX_REF_RE.match(ref_line)
    term = term_line.strip('" ')
    if not match or not 1 < len(term) <= 80 or not term[0].isupper():
        return None
    if INDEX_REF_RE.match(term) or SECTION_RE.match(term) or ARTICLE_RE.match(term):
        return None
    return term, match["ref"]


def _looks_like_index(run: list[tuple[str, str]]) -> bool:
    """An index lists terms alphabetically, so its references jump around and often
    point at subsections. A contents page has the same term/number rhythm, but its
    numbers only go up and never have subsections."""
    if len(run) < 5:
        return False
    keys = [section_key(ref) for _, ref in run]
    if any(key is None or key[2] for key in keys):
        return True  # "Preamble", "Recitals" or a subsection such as 6.2(a)
    numbers = [key[:2] for key in keys if key is not None]
    return numbers != sorted(numbers)


def term_index(lines: list[str]) -> dict[str, str]:
    """Read 'Term' / 'Section' pairs from index-of-defined-terms tables, wherever they are."""
    index: dict[str, str] = {}
    i = 0
    while i < len(lines) - 1:
        run: list[tuple[str, str]] = []
        j, missed = i, False
        while j < len(lines) - 1:
            pair = _index_pair(lines[j], lines[j + 1])
            if pair:
                run.append(pair)
                j, missed = j + 2, False
            elif run and not missed:
                j, missed = j + 1, True  # tolerate one stray line, such as a column header
            else:
                break
        if _looks_like_index(run):
            for term, ref in run:
                index.setdefault(term, ref)
            i = j
        else:
            i += 1
    return index


# --- annexes after the signature pages ----------------------------------------------------


def _annexes(tail: list[str]) -> tuple[list[Section], list[str], int]:
    """Split text after the signatures into annexes; keep definitions and conditions.

    Returns (kept annexes, titles of dropped annexes, characters not kept).
    """
    blocks: list[tuple[str, str, list[str]]] = []  # (label, title, lines)
    loose = 0
    for i, line in enumerate(tail):
        match = ANNEX_RE.match(line) if len(line) < 150 else None
        if match:
            label = f"{match['kind'].title()} {match['label'].upper()}"
            if blocks and blocks[-1][0] == label:
                continue  # the same heading repeated at the top of each page
            title = match["rest"].strip() or (tail[i + 1] if i + 1 < len(tail) else "")
            blocks.append((label, title, []))
        elif blocks:
            blocks[-1][2].append(line)
        else:
            loose += len(line)  # signature block itself

    kept: list[Section] = []
    dropped: list[str] = []
    dropped_chars = loose
    for label, title, lines in blocks:
        if KEEP_ANNEX_RE.search(title):
            body = lines[1:] if lines and lines[0] == title else lines
            kept.append(Section(ANNEX_ARTICLE, "ANNEXES", label, title, body))
        else:
            dropped.append(f"{label}: {title[:60]}")
            dropped_chars += sum(len(line) for line in lines)
    return kept, dropped, dropped_chars


# --- the parser --------------------------------------------------------------------------


def parse_structure(lines: list[str], deal_id: str = "") -> ParsedAgreement:
    start, method = find_body_start(lines)
    end, end_found = find_body_end(lines, start)
    body = lines[start:end]
    warnings: list[str] = []
    if method != "preamble":
        warnings.append(f"body start found by '{method}' rule, not the preamble")
    if not end_found:
        warnings.append("no end marker; signature pages may be in the last section")

    if len(lines) < 300 and sum(map(len, lines)) / max(len(lines), 1) > 1_000:
        warnings.append(
            "very few, very long lines: probably scanned page images with a hidden text layer"
        )
    # "ARTICLE" if the document has an ARTICLE I; otherwise "Section 1." is the top level.
    top_word = "ARTICLE" if any(_FIRST_ARTICLE_WORD.match(line) for line in body) else "SECTION"

    preamble: list[str] = []
    articles: list[Article] = []
    sections: list[Section] = []
    current: Section | None = None
    last_minor = 0

    i = 0
    while i < len(body):
        line = body[i]

        art = ARTICLE_RE.match(line)
        if art and art["word"].upper() == top_word and _is_article_heading(line, art["rest"]):
            number = article_number(art["num"])
            if number == len(articles) + 1:
                title, used = _article_title(art["rest"], body[i + 1 :])
                articles.append(Article(number, art["num"], title, top_word))
                current, last_minor = None, 0
                i += 1 + used
                continue

        sec = SECTION_RE.match(line)
        if sec and articles:
            major, minor = int(sec["major"]), int(sec["minor"])
            rest = sec["rest"].strip()
            plausible_rest = not rest or not (rest[0].islower() or rest[0] in "(0123456789")
            in_order = major == articles[-1].number and last_minor < minor <= last_minor + 3
            if plausible_rest and in_order:
                if minor > last_minor + 1:
                    warnings.append(
                        f"section numbering jumps from {major}.{last_minor} to {major}.{minor}"
                    )
                title, first_body, used = _section_title(sec["rest"], body[i + 1 :])
                article = articles[-1]
                current = Section(article.number, article.title, f"{major}.{sec['minor']}", title)
                if first_body:
                    current.lines.append(first_body)
                sections.append(current)
                last_minor = minor
                i += 1 + used
                continue

        if current is not None:
            current.lines.append(line)
        elif not articles:
            preamble.append(line)
        # Text between an article heading and its first section is rare; it is dropped.
        i += 1

    kept_annexes, dropped_annexes, trailing_chars = _annexes(lines[end:])
    sections.extend(kept_annexes)

    definitions: list[Definition] = []
    for section in sections:
        found = _definitions(section)
        definitions.extend(found)
        terms = {m["term"] for m in INLINE_TERM_RE.finditer(section.text)}
        terms.update(d.term for d in found)
        section.defined_terms = sorted(terms)

    if not articles:
        warnings.append("no ARTICLE headings found")
    for article in articles:
        if not any(s.article_number == article.number for s in sections):
            warnings.append(f"article {article.label} has no sections")
    for section in sections:
        if not section.title:
            warnings.append(f"section {section.number} has no title")
        if not section.lines and "reserved" not in section.title.lower():
            warnings.append(f"section {section.number} is empty")
        if len(section.text) > 60_000:
            warnings.append(
                f"section {section.number} is {len(section.text):,} chars; headings may be missed"
            )
    if not definitions:
        warnings.append("no definitions found")

    return ParsedAgreement(
        deal_id=deal_id,
        preamble="\n".join(preamble),
        articles=articles,
        sections=sections,
        definitions=definitions,
        term_index=term_index(lines),
        body_start_method=method,
        end_marker_found=end_found,
        dropped_annexes=dropped_annexes,
        trailing_chars=trailing_chars,
        warnings=warnings,
    )
