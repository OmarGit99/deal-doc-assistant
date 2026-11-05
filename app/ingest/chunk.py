"""Turn a parsed agreement into retrieval chunks, each with a context header and metadata."""

import hashlib
import re
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.ingest.sections import ANNEX_ARTICLE, Article, ParsedAgreement, Section

ChunkKind = Literal["preamble", "section", "definition", "annex"]

# Sizes are in characters, estimated at ~4 per token for English legal text. Close enough
# for sizing; swap in a real tokenizer once the embedding model is chosen.
CHARS_PER_TOKEN = 4
DEFAULT_CHUNK_TOKENS = 1000
DEFAULT_OVERLAP_TOKENS = 100
HEADER_ALLOWANCE = 300  # characters reserved for the context header
MIN_RESIDUAL_CHARS = 200  # leftover text in a definitions section worth its own chunk

# Paragraph breaks first, then clause and sentence ends, so splits fall where a lawyer would.
SEPARATORS = ["\n", "; ", ". ", " ", ""]


@dataclass(frozen=True)
class DealInfo:
    deal_id: str
    target: str
    acquirer: str
    source_url: str


@dataclass
class Chunk:
    chunk_id: str
    kind: ChunkKind
    deal_id: str
    target: str
    acquirer: str
    source_url: str
    article: str  # "ARTICLE 11 MISCELLANEOUS"; empty for the preamble and annexes
    section_number: str  # "11.04", "Annex I", "Preamble"
    section_title: str
    part: int  # 1-based position when a section is split
    parts: int
    header: str
    body: str  # agreement text only: citation quotes are checked against this
    term: str | None = None  # set on definition chunks
    defined_terms: list[str] = field(default_factory=list)
    page: int | None = None  # HTML exhibits have no reliable page numbers

    @property
    def text(self) -> str:
        """What gets embedded and keyword-indexed: header plus body."""
        return f"{self.header}\n\n{self.body}"

    @property
    def text_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def metadata(self) -> dict[str, Any]:
        meta = asdict(self)
        del meta["body"]  # stored once, as the document text
        meta["text_hash"] = self.text_hash
        return meta

    def to_document(self) -> Document:
        return Document(id=self.chunk_id, page_content=self.text, metadata=self.metadata())


def make_splitter(
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS, overlap_tokens: int = DEFAULT_OVERLAP_TOKENS
) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_tokens * CHARS_PER_TOKEN - HEADER_ALLOWANCE,
        chunk_overlap=overlap_tokens * CHARS_PER_TOKEN,
        separators=SEPARATORS,
        keep_separator="end",  # "; " and ". " stay with the clause they end
        strip_whitespace=True,
    )


def slug(value: str) -> str:
    """'Annex I' -> 'annex-i', '11.04' -> '11.04', 'Company MAE' -> 'company-mae'."""
    return re.sub(r"[^a-z0-9.]+", "-", value.lower()).strip("-")


class _Ids:
    """Hands out readable chunk ids and keeps them unique within a deal."""

    def __init__(self) -> None:
        self.seen: set[str] = set()

    def take(self, base: str) -> str:
        candidate, n = base, 2
        while candidate in self.seen:
            candidate, n = f"{base}-{n}", n + 1
        self.seen.add(candidate)
        return candidate


def _section_label(section: Section) -> str:
    if section.article_number == ANNEX_ARTICLE:
        return f"{section.number} {section.title}".strip()
    return f"Section {section.number} {section.title}".strip()


def _header(deal: DealInfo, *parts: str, part: int = 1, parts_total: int = 1) -> str:
    text = " · ".join([f"Deal: {deal.target} / {deal.acquirer}", *[p for p in parts if p]])
    return f"{text} (part {part}/{parts_total})" if parts_total > 1 else text


def _body_lines(section: Section, parsed: ParsedAgreement) -> list[str]:
    """Lines of a section that are not already covered by definition chunks.

    A definitions section is mostly list entries. Each entry becomes its own chunk, so the
    section keeps only what is left (an intro, an index table). Elsewhere a stray list
    definition is a small part of the section, and the section stays whole.
    """
    entries = [d for d in parsed.definitions if d.section_number == section.number and not d.inline]
    defined_chars = sum(len(d.text) for d in entries)
    if not entries or defined_chars < 0.5 * len(section.text):
        return section.lines
    covered = {line for d in entries for line in d.text.split("\n")}
    return [line for line in section.lines if line not in covered]


def chunk_agreement(
    parsed: ParsedAgreement,
    deal: DealInfo,
    *,
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    splitter = make_splitter(chunk_tokens, overlap_tokens)
    ids = _Ids()
    articles: dict[int, Article] = {a.number: a for a in parsed.articles}
    titles = {s.number: s.title for s in parsed.sections}
    chunks: list[Chunk] = []

    def emit(
        kind: ChunkKind,
        id_base: str,
        article: str,
        number: str,
        title: str,
        label: str,
        pieces: list[str],
        term: str | None = None,
        terms: list[str] | None = None,
    ) -> None:
        for i, piece in enumerate(pieces, start=1):
            chunks.append(
                Chunk(
                    chunk_id=ids.take(f"{id_base}-{i:02d}"),
                    kind=kind,
                    deal_id=deal.deal_id,
                    target=deal.target,
                    acquirer=deal.acquirer,
                    source_url=deal.source_url,
                    article=article,
                    section_number=number,
                    section_title=title,
                    part=i,
                    parts=len(pieces),
                    header=_header(deal, article, label, part=i, parts_total=len(pieces)),
                    body=piece,
                    term=term,
                    defined_terms=[t for t in terms or [] if f'"{t}"' in piece],
                )
            )

    if parsed.preamble:
        pieces = splitter.split_text(parsed.preamble)
        emit(
            "preamble",
            id_base=f"{deal.deal_id}-preamble",
            article="",
            number="Preamble",
            title="Preamble and Recitals",
            label="Preamble and Recitals",
            pieces=pieces,
        )

    for section in parsed.sections:
        text = "\n".join(_body_lines(section, parsed))
        if section.lines and text != section.text and len(text) < MIN_RESIDUAL_CHARS:
            continue  # a definitions section with nothing left over
        pieces = splitter.split_text(text)
        if not pieces:
            continue  # "[Reserved]" and other empty sections
        if section.article_number == ANNEX_ARTICLE:
            kind: ChunkKind = "annex"
            article = ""
        else:
            kind = "section"
            a = articles[section.article_number]
            article = f"{a.word} {a.label} {a.title}".strip()
        emit(
            kind,
            id_base=f"{deal.deal_id}-{slug(section.number)}",
            article=article,
            number=section.number,
            title=section.title,
            label=_section_label(section),
            pieces=pieces,
            terms=section.defined_terms,
        )

    for definition in parsed.definitions:
        pieces = splitter.split_text(definition.text)
        where = definition.section_number
        location = where if not re.match(r"\d", where) else f"Section {where}"
        emit(
            "definition",
            id_base=f"{deal.deal_id}-def-{slug(definition.term)}",
            article="",
            number=where,
            title=titles.get(where, ""),
            label=f'Definition of "{definition.term}" ({location})',
            pieces=pieces,
            term=definition.term,
        )

    return chunks


def chunk_stats(chunks: list[Chunk]) -> dict[str, Any]:
    """Counts by kind and estimated token sizes, for the ingest report."""
    tokens = sorted(len(c.text) // CHARS_PER_TOKEN for c in chunks)
    by_kind: dict[str, int] = {}
    for c in chunks:
        by_kind[c.kind] = by_kind.get(c.kind, 0) + 1
    if not tokens:
        return {"chunks": 0, "by_kind": by_kind}
    return {
        "chunks": len(chunks),
        "by_kind": by_kind,
        "tokens_p50": int(statistics.median(tokens)),
        "tokens_p95": tokens[min(len(tokens) - 1, int(len(tokens) * 0.95))],
        "tokens_max": tokens[-1],
    }
