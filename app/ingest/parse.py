"""Turn an EDGAR exhibit (HTML) into clean lines, and find where the body starts and ends."""

import re

from bs4 import BeautifulSoup

from app.text import normalize

# Tags that a browser renders on their own line (or cell).
BLOCK_TAGS = [
    "p", "div", "br", "tr", "td", "th", "li", "table", "center", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd", "blockquote", "pre",
]  # fmt: skip

# Marks the edges of block tags. A private-use character never appears in filings.
_BREAK = "\ue000"

# Lines that are page furniture, not agreement text.
_PAGE_ARTIFACTS = [
    re.compile(r"^(?:page\s+)?(?:[A-Z]{1,2}-)?\d{1,3}$", re.IGNORECASE),  # 12, A-12, Page 12
    re.compile(r"^-\s*\d{1,3}\s*-$"),  # - 12 -
    re.compile(r"^[ivxlc]{1,6}$"),  # lowercase roman page numbers in front matter
    re.compile(r"^table of contents(?: \(cont(?:inued|\.)\))?$", re.IGNORECASE),
    re.compile(r"^\[.*intentionally left blank.*\]\.?$", re.IGNORECASE),
]

# The preamble names the document. Seen so far:
#   (this "Agreement")   ("Agreement")   (this "Agreement" and, such date, ...)
#   (as amended from time to time, this "Agreement")
# Contents pages never do.
_PREAMBLE = re.compile(
    r'\((?:this|the)?\s*"Agreement"|(?:this|the)\s+"Agreement"\s*\)', re.IGNORECASE
)
_FIRST_ARTICLE = re.compile(r"^ARTICLE\s+(?:I|1|ONE)\b", re.IGNORECASE)
_END_MARKER = re.compile(r"^IN WITNESS WHEREOF", re.IGNORECASE)
# "[Signature Page Follows]", "[Remainder of page intentionally left blank; signature pages follow]"
SIGNATURES_FOLLOW = re.compile(r"signature pages?\s+(?:follows?|to follow)", re.IGNORECASE)


def html_to_lines(markup: str) -> list[str]:
    """One normalized line per rendered block, with page numbers and blank lines removed."""
    soup = BeautifulSoup(markup, "html.parser")
    for tag in soup(["script", "style", "head", "title"]):
        tag.decompose()
    for tag in soup.find_all(BLOCK_TAGS):
        tag.insert_before(_BREAK)
        tag.insert_after(_BREAK)
    # Inline tags (<font>, <b>, <span>) are joined with no separator, so a word split
    # across two tags comes back whole. Newlines in the HTML source are just wrapping
    # (normalize turns them into spaces); only the block markers end a line.
    text = soup.get_text("")
    lines: list[str] = []
    for raw in text.split(_BREAK):
        line = normalize(raw)
        if not line:
            continue
        # Keep "signature pages follow" lines: they mark the end of the body.
        if SIGNATURES_FOLLOW.search(line) or not any(p.match(line) for p in _PAGE_ARTIFACTS):
            lines.append(line)
    return lines


def find_body_start(lines: list[str]) -> tuple[int, str]:
    """Index of the first body line, and which rule found it.

    1. "preamble": the first long line that says (this "Agreement"). Everything before
       it (cover page, table of contents, index of defined terms) is front matter.
    2. "article": fallback for odd preambles. The last "ARTICLE I" heading that is
       followed by real prose within 15 lines. Contents pages only have short lines.
    3. "none": nothing matched; the caller warns.
    """
    for i, line in enumerate(lines):
        if len(line) > 100 and _PREAMBLE.search(line):
            return i, "preamble"
    candidates = [i for i, line in enumerate(lines) if _FIRST_ARTICLE.match(line)]
    for i in reversed(candidates):
        if any(len(line) > 200 for line in lines[i + 1 : i + 16]):
            return i, "article"
    return 0, "none"


def find_body_end(lines: list[str], start: int) -> tuple[int, bool]:
    """Index just past the last body line.

    The body ends at whichever comes first: a "[Signature Page Follows]" style line, or
    the "IN WITNESS WHEREOF" line that opens the signature block.
    """
    for i in range(start, len(lines)):
        line = lines[i]
        if _END_MARKER.match(line) or (len(line) < 200 and SIGNATURES_FOLLOW.search(line)):
            return i, True
    return len(lines), False
