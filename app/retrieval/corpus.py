"""Chunks as retrieval sees them, loaded from the chunk table."""

from dataclasses import dataclass, field
from typing import Any

from langchain_core.documents import Document
from sqlalchemy import Engine, text


@dataclass
class Candidate:
    """A chunk in a result list, with how each retrieval stage ranked it."""

    chunk_id: str
    deal_id: str
    section_number: str
    kind: str
    text: str  # header + body, exactly as indexed
    metadata: dict[str, Any] = field(default_factory=dict)
    bm25_rank: int | None = None
    bm25_score: float | None = None
    vector_rank: int | None = None
    vector_distance: float | None = None
    fused_score: float = 0.0
    rerank_score: float | None = None

    @property
    def header(self) -> str:
        return self.text.split("\n\n", 1)[0]

    @property
    def body(self) -> str:
        """Agreement text only. Citation quotes are checked against this, never the header."""
        return self.text.split("\n\n", 1)[-1]

    @property
    def section_title(self) -> str:
        return str(self.metadata.get("section_title", ""))

    @classmethod
    def from_document(cls, doc: Document) -> "Candidate":
        meta = doc.metadata
        return cls(
            chunk_id=str(doc.id),
            deal_id=meta["deal_id"],
            section_number=meta["section_number"],
            kind=meta["kind"],
            text=doc.page_content,
            metadata=meta,
        )


def load_corpus(engine: Engine, table: str) -> list[Candidate]:
    """Every stored chunk, for building the in-memory BM25 index at startup."""
    query = text(
        f"SELECT chunk_id, deal_id, section_number, kind, content, langchain_metadata "
        f'FROM "{table}" ORDER BY chunk_id'
    )
    with engine.connect() as conn:
        rows = conn.execute(query).all()
    corpus = []
    for chunk_id, deal_id, section_number, kind, content, extra in rows:
        metadata = {
            **(extra or {}),
            "deal_id": deal_id,
            "section_number": section_number,
            "kind": kind,
        }
        corpus.append(Candidate(chunk_id, deal_id, section_number, kind, content, metadata))
    return corpus
