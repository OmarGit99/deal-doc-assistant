"""Assemble the retriever from settings. Called once at startup (scripts, later the API)."""

from langchain_postgres import PGEngine

from app.config import Settings
from app.db import make_engine
from app.embeddings import make_embeddings
from app.ingest.store import open_store
from app.retrieval.bm25 import BM25Index
from app.retrieval.corpus import load_corpus
from app.retrieval.hybrid import DEFAULT_CONFIG, HybridRetriever, RetrievalConfig
from app.retrieval.rerank import FlashRankReranker, Reranker


def build_retriever(
    settings: Settings,
    *,
    reranker: Reranker | None = None,
    config: RetrievalConfig = DEFAULT_CONFIG,
) -> HybridRetriever:
    engine = make_engine(settings.database_url)
    corpus = load_corpus(engine, settings.chunks_table)
    if not corpus:
        raise RuntimeError(f"{settings.chunks_table} is empty; run scripts.ingest first")
    store = open_store(
        PGEngine.from_connection_string(settings.database_url),
        make_embeddings(settings),
        settings.chunks_table,
    )
    return HybridRetriever(BM25Index(corpus), store, reranker or FlashRankReranker(), config)
