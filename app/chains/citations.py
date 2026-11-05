"""The citation validator: code, not the model, decides whether a citation is real."""

from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.ingest.sections import section_matches
from app.retrieval.corpus import Candidate
from app.text import contains_quote, normalize

MIN_QUOTE_CHARS = 6  # shorter "quotes" (such as "the") would match almost anything


class Citation(BaseModel):
    chunk_id: str = Field(description="The chunk_id attribute of the section being quoted")
    section_number: str = Field(description="Most specific section number, e.g. 11.04(b)")
    quote: str = Field(description="Exact words copied from that section, under 40 words")


@dataclass(frozen=True)
class Rejected:
    citation: Citation
    reason: str


def validate_citations(
    citations: list[Citation], retrieved: list[Candidate]
) -> tuple[list[Citation], list[Rejected]]:
    """Keep a citation only if it points at a chunk that was retrieved for this question
    and its quote really appears in that chunk's body (not its header).

    The section number is trusted only if it falls inside the chunk's section; a model
    that cites "8.3(b)" for a quote from chunk 11.04 gets the chunk's own number instead.
    """
    by_id = {c.chunk_id: c for c in retrieved}
    valid: list[Citation] = []
    rejected: list[Rejected] = []
    seen: set[tuple[str, str]] = set()
    for citation in citations:
        chunk = by_id.get(citation.chunk_id)
        if chunk is None:
            rejected.append(Rejected(citation, "chunk was not retrieved"))
            continue
        if len(normalize(citation.quote)) < MIN_QUOTE_CHARS:
            rejected.append(Rejected(citation, "quote too short to verify"))
            continue
        if not contains_quote(chunk.body, citation.quote):
            rejected.append(Rejected(citation, "quote not found in the chunk"))
            continue
        key = (citation.chunk_id, normalize(citation.quote))
        if key in seen:
            continue
        seen.add(key)
        section = citation.section_number
        if not section_matches(section, chunk.section_number):
            section = chunk.section_number
        valid.append(citation.model_copy(update={"section_number": section}))
    return valid, rejected
