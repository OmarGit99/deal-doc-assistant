import os
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from langchain_core.documents import Document
from langchain_postgres import PGEngine
from sqlalchemy import Engine, text

from app.config import Settings
from app.db import make_engine
from app.embeddings import make_embeddings
from app.ingest.chunk import DealInfo, chunk_agreement
from app.ingest.parse import html_to_lines
from app.ingest.sections import parse_structure
from app.ingest.store import ensure_chunk_table, open_store, sync_deal
from app.retrieval.bm25 import BM25Index, tokenize
from app.retrieval.corpus import Candidate, load_corpus
from app.retrieval.hybrid import HybridRetriever, RetrievalConfig, reciprocal_rank_fusion
from app.retrieval.rerank import FlashRankReranker
from tests.agreement_fixtures import ARABIC_PREFIXED

HEADER = "Deal: T / A · Section"


def cand(chunk_id: str, body: str, deal_id: str = "deal-a", section: str = "1.01") -> Candidate:
    meta = {"deal_id": deal_id, "section_number": section, "kind": "section"}
    return Candidate(chunk_id, deal_id, section, "section", f"{HEADER} {section}\n\n{body}", meta)


CORPUS = [
    cand(
        "a-fee", "The Company shall pay Parent a termination fee of $407,500,000.", section="11.04"
    ),
    cand("a-date", "The End Date is January 9, 2025, extended to April 9, 2025.", section="10.01"),
    cand("a-law", "This Agreement shall be governed by the laws of Delaware.", section="11.07"),
    cand("b-fee", "Parent shall pay a termination fee of $266,400,000.", "deal-b", "8.5"),
]


class FakeVectors:
    """Returns the corpus in a fixed order, honouring the deal filter like PGVectorStore."""

    def __init__(self, order: list[str]) -> None:
        self.order = order
        self.filters: list[dict[str, Any] | None] = []

    def similarity_search_with_score(
        self, query: str, k: int | None = None, filter: dict[str, Any] | None = None
    ) -> list[tuple[Document, float]]:
        self.filters.append(filter)
        allowed = set(filter["deal_id"]["$in"]) if filter else None
        by_id = {c.chunk_id: c for c in CORPUS}
        hits = [by_id[i] for i in self.order if allowed is None or by_id[i].deal_id in allowed]
        return [
            (Document(id=c.chunk_id, page_content=c.text, metadata=c.metadata), 0.1 * rank)
            for rank, c in enumerate(hits[:k], start=1)
        ]


class OverlapReranker:
    """Scores by word overlap with the query: crude, but deterministic and offline."""

    def score(self, query: str, texts: list[str]) -> list[float]:
        words = set(tokenize(query))
        return [len(words & set(tokenize(t))) / max(len(words), 1) for t in texts]


# --- tokenizer and BM25 -----------------------------------------------------------------


def test_tokenize_keeps_amounts_and_section_numbers() -> None:
    tokens = tokenize("Section 11.04(b) fee of $407,500,000 and $40.00 per Share")
    assert "11.04" in tokens and "407,500,000" in tokens and "40.00" in tokens
    assert "b" not in tokens  # subsection letters are noise
    assert "of" not in tokens and "and" not in tokens


def test_bm25_ranks_exact_terms_first() -> None:
    hits = BM25Index(CORPUS).search("When is the End Date?", None, k=3)
    assert hits[0].chunk_id == "a-date"
    assert hits[0].bm25_rank == 1 and hits[0].bm25_score and hits[0].bm25_score > 0


def test_bm25_respects_the_deal_filter() -> None:
    hits = BM25Index(CORPUS).search("termination fee", ["deal-b"], k=5)
    assert [h.chunk_id for h in hits] == ["b-fee"]


def test_bm25_returns_nothing_without_matching_words() -> None:
    assert BM25Index(CORPUS).search("zebra", None, k=5) == []


def test_bm25_rejects_an_empty_corpus() -> None:
    with pytest.raises(ValueError):
        BM25Index([])


# --- fusion -------------------------------------------------------------------------------


def test_rrf_uses_ranks_and_weights() -> None:
    a, b, c = cand("a", "x"), cand("b", "x"), cand("c", "x")
    fused = reciprocal_rank_fusion([[a, b], [b, c]], [0.5, 0.5], c=60)
    scores = {x.chunk_id: round(x.fused_score, 6) for x in fused}
    assert scores == {
        "b": round(0.5 / 62 + 0.5 / 61, 6),  # 2nd in one list, 1st in the other
        "a": round(0.5 / 61, 6),
        "c": round(0.5 / 62, 6),
    }
    assert [x.chunk_id for x in fused] == ["b", "a", "c"]


def test_rrf_keeps_both_stage_ranks_on_merged_candidates() -> None:
    from_bm25 = BM25Index(CORPUS).search("termination fee", ["deal-a"], k=3)
    from_vector = [
        Candidate(**{**cand("a-fee", "x").__dict__, "vector_rank": 2, "vector_distance": 0.3})
    ]
    [merged] = [
        c
        for c in reciprocal_rank_fusion([from_bm25, from_vector], [0.5, 0.5])
        if c.chunk_id == "a-fee"
    ]
    assert merged.bm25_rank == 1 and merged.vector_rank == 2


# --- the retriever --------------------------------------------------------------------------


def retriever(vector_order: list[str]) -> tuple[HybridRetriever, FakeVectors]:
    vectors = FakeVectors(vector_order)
    return HybridRetriever(BM25Index(CORPUS), vectors, OverlapReranker()), vectors


def test_modes_return_what_each_stage_found() -> None:
    hr, _ = retriever(["a-law", "a-date", "a-fee"])
    query = "termination fee amount"
    vector = hr.retrieve(query, ["deal-a"], RetrievalConfig(mode="vector", top_k=2))
    assert [c.chunk_id for c in vector.candidates] == ["a-law", "a-date"]
    bm25 = hr.retrieve(query, ["deal-a"], RetrievalConfig(mode="bm25", top_k=2))
    assert bm25.candidates[0].chunk_id == "a-fee"
    hybrid = hr.retrieve(query, ["deal-a"], RetrievalConfig(mode="hybrid", top_k=3))
    assert {c.chunk_id for c in hybrid.candidates} == {"a-fee", "a-law", "a-date"}
    assert set(hybrid.timings_ms) == {"bm25", "vector"}


def test_reranking_reorders_the_fused_pool() -> None:
    # Vector search puts the fee chunk last; the reranker reads it and moves it to the top.
    hr, _ = retriever(["a-law", "a-date", "a-fee"])
    result = hr.retrieve("termination fee payable", ["deal-a"], RetrievalConfig(top_k=2))
    assert result.candidates[0].chunk_id == "a-fee"
    assert result.best_rerank_score == result.candidates[0].rerank_score
    assert "rerank" in result.timings_ms


def test_deal_filter_reaches_vector_search() -> None:
    hr, vectors = retriever(["b-fee", "a-fee"])
    result = hr.retrieve("termination fee", ["deal-b"])
    assert vectors.filters[-1] == {"deal_id": {"$in": ["deal-b"]}}
    assert {c.deal_id for c in result.candidates} == {"deal-b"}


def test_candidate_splits_header_from_body() -> None:
    c = CORPUS[0]
    assert c.header == f"{HEADER} 11.04"
    assert c.body.startswith("The Company shall pay")


def test_flashrank_scores_map_back_to_input_order() -> None:
    class FakeRanker:
        def rerank(self, request: Any) -> list[dict[str, Any]]:
            # FlashRank returns results sorted by score, not in input order.
            return [{"id": 1, "score": 0.9}, {"id": 0, "score": 0.2}]

    reranker = FlashRankReranker()
    reranker._ranker = FakeRanker()
    assert reranker.score("q", ["first", "second"]) == [0.2, 0.9]
    assert reranker.score("q", []) == []


# --- against Postgres -----------------------------------------------------------------------

DB_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def stored_table() -> Iterator[tuple[Engine, str, Settings]]:
    if not DB_URL:
        pytest.skip("set TEST_DATABASE_URL to run")
    settings = Settings(database_url=DB_URL, embedding_provider="fake", embedding_dimensions=32)
    engine = make_engine(DB_URL)
    table = f"test_chunks_{uuid.uuid4().hex[:8]}"
    pg = PGEngine.from_connection_string(DB_URL)
    ensure_chunk_table(pg, engine, table, 32)
    store = open_store(pg, make_embeddings(settings), table)
    deal = DealInfo("juniper-hpe-2024", "Juniper", "HPE", "https://x")
    chunks = chunk_agreement(parse_structure(html_to_lines(ARABIC_PREFIXED)), deal)
    sync_deal(store, engine, table, deal.deal_id, chunks)
    yield engine, table, settings
    with engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{table}"'))
    engine.dispose()


def test_corpus_loads_from_the_chunk_table(stored_table: tuple[Engine, str, Settings]) -> None:
    engine, table, _ = stored_table
    corpus = load_corpus(engine, table)
    by_id = {c.chunk_id: c for c in corpus}
    chunk = by_id["juniper-hpe-2024-2.02-01"]
    assert chunk.section_number == "2.02"
    assert chunk.section_title == "Conversion of Shares"
    assert "$40.00 per Share" in chunk.body


def test_hybrid_retrieval_end_to_end(stored_table: tuple[Engine, str, Settings]) -> None:
    engine, table, settings = stored_table
    store = open_store(PGEngine.from_connection_string(settings.database_url),
                       make_embeddings(settings), table)  # fmt: skip
    hr = HybridRetriever(BM25Index(load_corpus(engine, table)), store, OverlapReranker())
    result = hr.retrieve("price of $40.00 per Share in cash", ["juniper-hpe-2024"])
    assert result.candidates[0].section_number == "2.02"
    assert all(c.deal_id == "juniper-hpe-2024" for c in result.candidates)
    assert hr.retrieve("price per Share", ["some-other-deal"]).candidates == []


def test_idf_stays_positive_for_common_words() -> None:
    # "fee" appears in 2 of 4 chunks: plain BM25Okapi would give it zero weight.
    hits = BM25Index(CORPUS).search("fee", None, k=5)
    assert {h.chunk_id for h in hits} == {"a-fee", "b-fee"}
