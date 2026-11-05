"""Storage tests. The database tests need a real Postgres with pgvector:

    $env:TEST_DATABASE_URL = "postgresql+psycopg://deal:<password>@localhost:5433/dealdocs"
    uv run pytest tests/test_store.py

Without TEST_DATABASE_URL they are skipped, so the unit test run stays offline.
"""

import os
import uuid
from collections.abc import Iterator
from dataclasses import replace
from datetime import date

import pytest
from langchain_postgres import PGEngine
from sqlalchemy import Engine, text

from app.config import Settings
from app.db import DealRow, ensure_deals_table, list_deals, make_engine, upsert_deals
from app.embeddings import make_embeddings
from app.ingest.chunk import Chunk, DealInfo, chunk_agreement
from app.ingest.parse import html_to_lines
from app.ingest.sections import parse_structure
from app.ingest.store import (
    ensure_chunk_table,
    open_store,
    plan_sync,
    stored_hashes,
    sync_deal,
)
from tests.agreement_fixtures import ARABIC_PREFIXED

DEAL = DealInfo("juniper-hpe-2024", "Juniper Networks, Inc.", "HPE", "https://www.sec.gov/x")
DB_URL = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DB_URL, reason="set TEST_DATABASE_URL to run")


def sample_chunks() -> list[Chunk]:
    return chunk_agreement(parse_structure(html_to_lines(ARABIC_PREFIXED)), DEAL)


# --- settings and planning (no database) --------------------------------------------------


def test_table_name_encodes_the_embedding_configuration() -> None:
    settings = Settings(database_url="postgresql+psycopg://x@y/z")
    assert settings.chunks_table == "chunks_text_embedding_3_small_1536"
    other = Settings(
        database_url="x", embedding_model="BAAI/bge-small-en-v1.5", embedding_dimensions=384
    )
    assert other.chunks_table == "chunks_baai_bge_small_en_v1_5_384"


def test_openai_provider_requires_a_key() -> None:
    settings = Settings(database_url="x", embedding_provider="openai", openai_api_key=None)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        make_embeddings(settings)


def test_plan_sync_embeds_only_new_and_changed_chunks() -> None:
    chunks = sample_chunks()
    stored = {c.chunk_id: c.text_hash for c in chunks}
    stored[chunks[0].chunk_id] = "old-hash"  # changed
    del stored[chunks[1].chunk_id]  # new
    stored["juniper-hpe-2024-9.99-01"] = "gone"  # no longer produced
    to_embed, to_delete = plan_sync(stored, chunks)
    assert [c.chunk_id for c in to_embed] == [chunks[0].chunk_id, chunks[1].chunk_id]
    assert to_delete == ["juniper-hpe-2024-9.99-01"]


# --- against Postgres -------------------------------------------------------------------


@pytest.fixture
def engine() -> Iterator[Engine]:
    assert DB_URL
    eng = make_engine(DB_URL)
    yield eng
    eng.dispose()


@pytest.fixture
def table(engine: Engine) -> Iterator[str]:
    name = f"test_chunks_{uuid.uuid4().hex[:8]}"
    yield name
    with engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{name}"'))


def fake_settings() -> Settings:
    assert DB_URL
    return Settings(database_url=DB_URL, embedding_provider="fake", embedding_dimensions=32)


@needs_db
def test_sync_is_idempotent_and_removes_stale_chunks(engine: Engine, table: str) -> None:
    settings = fake_settings()
    pg_engine = PGEngine.from_connection_string(settings.database_url)
    ensure_chunk_table(pg_engine, engine, table, settings.embedding_dimensions)
    store = open_store(pg_engine, make_embeddings(settings), table)
    chunks = sample_chunks()

    first = sync_deal(store, engine, table, DEAL.deal_id, chunks, batch_size=4)
    assert (first.embedded, first.unchanged, first.deleted) == (len(chunks), 0, 0)

    second = sync_deal(store, engine, table, DEAL.deal_id, chunks)
    assert (second.embedded, second.unchanged, second.deleted) == (0, len(chunks), 0)

    edited = [replace(chunks[0], body=chunks[0].body + " Amended."), *chunks[1:-1]]
    third = sync_deal(store, engine, table, DEAL.deal_id, edited)
    assert (third.embedded, third.deleted) == (1, 1)
    hashes = stored_hashes(engine, table, DEAL.deal_id)
    assert set(hashes) == {c.chunk_id for c in edited}
    assert hashes[edited[0].chunk_id] == edited[0].text_hash


@needs_db
def test_stored_chunk_round_trips_with_metadata(engine: Engine, table: str) -> None:
    settings = fake_settings()
    pg_engine = PGEngine.from_connection_string(settings.database_url)
    ensure_chunk_table(pg_engine, engine, table, settings.embedding_dimensions)
    store = open_store(pg_engine, make_embeddings(settings), table)
    chunks = sample_chunks()
    sync_deal(store, engine, table, DEAL.deal_id, chunks)

    target = next(c for c in chunks if c.section_number == "2.02")
    [doc] = store.get_by_ids([target.chunk_id])
    assert doc.page_content == target.text
    assert doc.metadata["section_number"] == "2.02"
    assert doc.metadata["defined_terms"] == ["Merger Consideration"]

    # The fake embedding maps identical text to an identical vector, so searching with
    # a chunk's exact text must return that chunk first, inside the deal filter.
    hits = store.similarity_search(target.text, k=1, filter={"deal_id": {"$in": [DEAL.deal_id]}})
    assert hits[0].id == target.chunk_id
    assert store.similarity_search(target.text, k=1, filter={"deal_id": {"$in": ["other"]}}) == []


@needs_db
def test_dry_run_writes_nothing(engine: Engine, table: str) -> None:
    result = sync_deal(None, engine, table, DEAL.deal_id, sample_chunks())
    assert result.embedded == len(sample_chunks())
    from sqlalchemy import inspect

    assert not inspect(engine).has_table(table)


@needs_db
def test_deals_table_upsert(engine: Engine) -> None:
    ensure_deals_table(engine)
    row = DealRow("test-deal-0000", "Target", "Acquirer", date(2024, 1, 9), "https://x")
    upsert_deals(engine, [row])
    upsert_deals(engine, [replace(row, acquirer="Acquirer Inc.")])
    try:
        stored = {d.deal_id: d for d in list_deals(engine)}["test-deal-0000"]
        assert stored.acquirer == "Acquirer Inc."
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM deals WHERE deal_id = 'test-deal-0000'"))
