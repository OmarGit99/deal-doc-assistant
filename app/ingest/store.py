"""The chunk table in Postgres/pgvector, and keeping it in sync with the chunker output."""

from collections.abc import Callable
from dataclasses import dataclass

from langchain_core.embeddings import Embeddings
from langchain_postgres import Column, ColumnDict, PGEngine, PGVectorStore
from sqlalchemy import Engine, inspect, text

from app.ingest.chunk import Chunk

ID_COLUMN = "chunk_id"
# Metadata stored as real columns so they can be filtered and indexed. Everything else
# goes into the JSON metadata column.
METADATA_COLUMN_NAMES = ["deal_id", "kind", "section_number", "text_hash"]
METADATA_COLUMNS: list[Column | ColumnDict] = [
    Column(name, "TEXT", nullable=False) for name in METADATA_COLUMN_NAMES
]


@dataclass
class SyncResult:
    deal_id: str
    embedded: int  # new or changed chunks sent to the embedding model
    unchanged: int
    deleted: int  # chunks in the table that the chunker no longer produces
    embedded_chars: int

    def estimated_cost(self, price_per_million_tokens: float, chars_per_token: int = 4) -> float:
        return self.embedded_chars / chars_per_token / 1_000_000 * price_per_million_tokens


def ensure_chunk_table(pg_engine: PGEngine, engine: Engine, table: str, dimensions: int) -> None:
    """Create the table on first use. Never drops or alters an existing one."""
    if inspect(engine).has_table(table):
        return
    pg_engine.init_vectorstore_table(
        table_name=table,
        vector_size=dimensions,
        id_column=Column(ID_COLUMN, "TEXT", nullable=False),
        metadata_columns=METADATA_COLUMNS,
    )
    with engine.begin() as conn:
        conn.execute(text(f'CREATE INDEX IF NOT EXISTS "{table}_deal_id" ON "{table}" (deal_id)'))


def open_store(pg_engine: PGEngine, embeddings: Embeddings, table: str) -> PGVectorStore:
    return PGVectorStore.create_sync(
        engine=pg_engine,
        embedding_service=embeddings,
        table_name=table,
        id_column=ID_COLUMN,
        metadata_columns=METADATA_COLUMN_NAMES,
    )


def stored_hashes(engine: Engine, table: str, deal_id: str) -> dict[str, str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(f'SELECT {ID_COLUMN}, text_hash FROM "{table}" WHERE deal_id = :deal_id'),
            {"deal_id": deal_id},
        )
        return {chunk_id: text_hash for chunk_id, text_hash in rows}


def plan_sync(stored: dict[str, str], chunks: list[Chunk]) -> tuple[list[Chunk], list[str]]:
    """Return (chunks to embed, chunk ids to delete). Unchanged chunks are left alone."""
    wanted = {c.chunk_id for c in chunks}
    to_embed = [c for c in chunks if stored.get(c.chunk_id) != c.text_hash]
    to_delete = sorted(chunk_id for chunk_id in stored if chunk_id not in wanted)
    return to_embed, to_delete


def sync_deal(
    store: PGVectorStore | None,
    engine: Engine,
    table: str,
    deal_id: str,
    chunks: list[Chunk],
    *,
    batch_size: int = 100,
    on_batch: Callable[[int, int], None] | None = None,
) -> SyncResult:
    """Make the table hold exactly `chunks` for this deal, embedding only what changed.

    Pass store=None for a dry run: the plan is computed but nothing is written.
    """
    stored = stored_hashes(engine, table, deal_id) if inspect(engine).has_table(table) else {}
    to_embed, to_delete = plan_sync(stored, chunks)
    result = SyncResult(
        deal_id=deal_id,
        embedded=len(to_embed),
        unchanged=len(chunks) - len(to_embed),
        deleted=len(to_delete),
        embedded_chars=sum(len(c.text) for c in to_embed),
    )
    if store is None:
        return result

    if to_delete:
        store.delete(ids=to_delete)
    for start in range(0, len(to_embed), batch_size):
        batch = to_embed[start : start + batch_size]
        # add_documents embeds the text and upserts on chunk_id, so a changed chunk
        # replaces its old row.
        store.add_documents([c.to_document() for c in batch], ids=[c.chunk_id for c in batch])
        if on_batch:
            on_batch(start + len(batch), len(to_embed))
    return result
