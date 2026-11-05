"""Parse, chunk, embed and store every downloaded agreement.

    uv run python -m scripts.ingest --dry-run      # what would be embedded, and the cost
    uv run python -m scripts.ingest                # do it
    uv run python -m scripts.ingest --deal juniper-hpe-2024 --show 3

Safe to re-run: unchanged chunks are skipped, changed ones re-embedded, and chunks the
chunker no longer produces are deleted.
"""

import argparse
import asyncio
import io
import json
import sys
from pathlib import Path

# Fix Psycopg async compatibility on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )

from langchain_postgres import PGEngine

from app.config import get_settings
from app.db import DealRow, ensure_deals_table, make_engine, upsert_deals
from app.embeddings import make_embeddings
from app.ingest.chunk import Chunk, DealInfo, chunk_agreement, chunk_stats
from app.ingest.edgar import SeedDeal, SeedError, cached_exhibit_path, load_seed
from app.ingest.parse import html_to_lines
from app.ingest.sections import parse_structure
from app.ingest.store import SyncResult, ensure_chunk_table, open_store, sync_deal
from app.text import decode_html


def write_jsonl(chunks: list[Chunk], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            record = {**chunk.metadata(), "text": chunk.text}
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_chunks(deal: SeedDeal, raw_dir: Path, chunk_tokens: int, overlap: int) -> list[Chunk]:
    path = cached_exhibit_path(deal, raw_dir)
    if not path.exists():
        raise ValueError("not downloaded")
    parsed = parse_structure(html_to_lines(decode_html(path.read_bytes())), deal.deal_id)
    if not parsed.articles:
        raise ValueError(f"no structure found ({'; '.join(parsed.warnings)})")
    info = DealInfo(deal.deal_id, deal.target, deal.acquirer, deal.exhibit_url)
    return chunk_agreement(parsed, info, chunk_tokens=chunk_tokens, overlap_tokens=overlap)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=Path, default=Path("scripts/seed_deals.csv"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/chunks"))
    parser.add_argument("--deal", action="append", default=[])
    parser.add_argument("--chunk-tokens", type=int, default=1000)
    parser.add_argument("--overlap-tokens", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    parser.add_argument("--show", type=int, default=0, help="print the first N chunks per deal")
    args = parser.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="replace")

    try:
        deals = load_seed(args.seed)
    except SeedError as exc:
        print(f"Seed file has problems:\n{exc}", file=sys.stderr)
        return 2
    if args.deal:
        deals = [d for d in deals if d.deal_id in args.deal]

    settings = get_settings()
    table = settings.chunks_table
    engine = make_engine(settings.database_url)
    store = None
    if not args.dry_run:
        ensure_deals_table(engine)
        pg_engine = PGEngine.from_connection_string(settings.database_url)
        ensure_chunk_table(pg_engine, engine, table, settings.embedding_dimensions)
        store = open_store(pg_engine, make_embeddings(settings), table)

    mode = "DRY RUN, nothing written" if args.dry_run else "writing"
    print(f"Table {table} ({settings.embedding_provider}: {settings.embedding_model}); {mode}\n")
    print(f"{'deal_id':<38} {'chunks':>6} {'embed':>6} {'same':>6} {'delete':>6}  max tokens")
    results: list[SyncResult] = []
    for deal in deals:
        try:
            chunks = build_chunks(deal, args.raw_dir, args.chunk_tokens, args.overlap_tokens)
        except ValueError as exc:
            print(f"{deal.deal_id:<38} skipped: {exc}")
            continue
        write_jsonl(chunks, args.out_dir / f"{deal.deal_id}.jsonl")
        if not args.dry_run:
            row = DealRow(
                deal.deal_id,
                deal.target,
                deal.acquirer,
                deal.announcement_date,
                deal.exhibit_url,
                deal.preamble_target,
                deal.preamble_acquirer,
            )
            upsert_deals(engine, [row])
        result = sync_deal(store, engine, table, deal.deal_id, chunks)
        results.append(result)
        print(
            f"{deal.deal_id:<38} {len(chunks):>6} {result.embedded:>6} {result.unchanged:>6} "
            f"{result.deleted:>6}  {chunk_stats(chunks)['tokens_max']:>5}"
        )
        for chunk in chunks[: args.show]:
            preview = chunk.body[:300].replace("\n", " / ")
            print(f"\n  [{chunk.chunk_id}]\n  {chunk.header}\n  {preview}...")

    embedded = sum(r.embedded for r in results)
    chars = sum(r.embedded_chars for r in results)
    cost = sum(r.estimated_cost(settings.embedding_price_per_million_tokens) for r in results)
    verb = "would embed" if args.dry_run else "embedded"
    print(
        f"\n{verb} {embedded:,} chunks (~{chars // 4:,} tokens, ~${cost:.4f}); "
        f"deleted {sum(r.deleted for r in results):,} stale chunks"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
