"""Hybrid retrieval: BM25 + vector search, fused with reciprocal rank fusion, then reranked."""

import time
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal, Protocol

from langchain_core.documents import Document

from app.retrieval.bm25 import BM25Index
from app.retrieval.corpus import Candidate
from app.retrieval.rerank import Reranker

Mode = Literal["vector", "bm25", "hybrid", "hybrid_rerank"]
MODES: tuple[Mode, ...] = ("vector", "bm25", "hybrid", "hybrid_rerank")


class VectorSearch(Protocol):
    """The one method used from PGVectorStore, so tests can pass a stand-in."""

    def similarity_search_with_score(
        self, query: str, k: int | None = None, filter: dict[str, Any] | None = None
    ) -> list[tuple[Document, float]]: ...


@dataclass(frozen=True)
class RetrievalConfig:
    mode: Mode = "hybrid_rerank"
    k_bm25: int = 20
    k_vector: int = 20
    bm25_weight: float = 0.5
    vector_weight: float = 0.5
    rrf_c: int = 60  # damping constant; 60 is the value from the original RRF paper
    rerank_pool: int = 20  # fused candidates sent to the reranker
    top_k: int = 5


DEFAULT_CONFIG = RetrievalConfig()


@dataclass
class RetrievalResult:
    candidates: list[Candidate]
    timings_ms: dict[str, float] = field(default_factory=dict)

    @property
    def best_rerank_score(self) -> float | None:
        scores = [c.rerank_score for c in self.candidates if c.rerank_score is not None]
        return max(scores) if scores else None


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[Candidate]], weights: Sequence[float], c: int = 60
) -> list[Candidate]:
    """score(chunk) = sum over lists of weight / (rank + c), with ranks starting at 1.

    Only ranks are used, never raw scores: BM25 scores and cosine distances are on
    different scales, but "3rd in one list" means the same thing everywhere. The same
    formula as LangChain's EnsembleRetriever.
    """
    merged: dict[str, Candidate] = {}
    for ranked, weight in zip(ranked_lists, weights, strict=True):
        for rank, cand in enumerate(ranked, start=1):
            current = merged.get(cand.chunk_id)
            if current is None:
                current = merged[cand.chunk_id] = replace(cand, fused_score=0.0)
            current.fused_score += weight / (rank + c)
            # Keep both stages' ranks on the merged candidate for debugging and ablation.
            if cand.bm25_rank is not None:
                current.bm25_rank, current.bm25_score = cand.bm25_rank, cand.bm25_score
            if cand.vector_rank is not None:
                current.vector_rank = cand.vector_rank
                current.vector_distance = cand.vector_distance
    return sorted(merged.values(), key=lambda cand: -cand.fused_score)


class HybridRetriever:
    def __init__(
        self,
        bm25: BM25Index,
        vectors: VectorSearch,
        reranker: Reranker | None,
        config: RetrievalConfig = DEFAULT_CONFIG,
    ) -> None:
        self.bm25 = bm25
        self.vectors = vectors
        self.reranker = reranker
        self.config = config

    def _vector_search(self, query: str, deal_ids: Sequence[str] | None, k: int) -> list[Candidate]:
        where = {"deal_id": {"$in": list(deal_ids)}} if deal_ids else None
        hits = self.vectors.similarity_search_with_score(query, k=k, filter=where)
        return [
            replace(Candidate.from_document(doc), vector_rank=rank, vector_distance=distance)
            for rank, (doc, distance) in enumerate(hits, start=1)
        ]

    def retrieve(
        self,
        query: str,
        deal_ids: Sequence[str] | None = None,
        config: RetrievalConfig | None = None,
    ) -> RetrievalResult:
        cfg = config or self.config
        timings: dict[str, float] = {}

        def timed(stage: str, start: float) -> None:
            timings[stage] = round((time.perf_counter() - start) * 1000, 1)

        lists: list[list[Candidate]] = []
        weights: list[float] = []
        if cfg.mode != "vector":
            start = time.perf_counter()
            lists.append(self.bm25.search(query, deal_ids, cfg.k_bm25))
            weights.append(cfg.bm25_weight)
            timed("bm25", start)
        if cfg.mode != "bm25":
            start = time.perf_counter()
            lists.append(self._vector_search(query, deal_ids, cfg.k_vector))
            weights.append(cfg.vector_weight)
            timed("vector", start)

        if cfg.mode in ("vector", "bm25"):
            return RetrievalResult(lists[0][: cfg.top_k], timings)

        fused = reciprocal_rank_fusion(lists, weights, cfg.rrf_c)
        if cfg.mode == "hybrid" or self.reranker is None:
            return RetrievalResult(fused[: cfg.top_k], timings)

        start = time.perf_counter()
        pool = fused[: cfg.rerank_pool]
        scores = self.reranker.score(query, [c.text for c in pool])
        for cand, score in zip(pool, scores, strict=True):
            cand.rerank_score = score
        reranked = sorted(pool, key=lambda cand: -(cand.rerank_score or 0.0))
        timed("rerank", start)
        return RetrievalResult(reranked[: cfg.top_k], timings)
