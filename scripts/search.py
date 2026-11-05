"""Vector search over stored chunks: a quick check that retrieval returns sensible sections.

uv run python -m scripts.search "What is the termination fee?" --deal juniper-hpe-2024
"""

import argparse
import io
import sys

from langchain_postgres import PGEngine

from app.config import get_settings
from app.embeddings import make_embeddings
from app.ingest.store import open_store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question")
    parser.add_argument("--deal", action="append", default=[], help="restrict to deal_id")
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="replace")

    settings = get_settings()
    store = open_store(
        PGEngine.from_connection_string(settings.database_url),
        make_embeddings(settings),
        settings.chunks_table,
    )
    where = {"deal_id": {"$in": args.deal}} if args.deal else None
    hits = store.similarity_search_with_score(args.question, k=args.k, filter=where)
    for rank, (doc, distance) in enumerate(hits, start=1):
        meta = doc.metadata
        body = doc.page_content.split("\n\n", 1)[-1][:240].replace("\n", " / ")
        print(f"{rank}. {distance:.3f}  {doc.id}")
        print(f"   {meta['deal_id']} | {meta['section_number']} {meta.get('section_title', '')}")
        print(f"   {body}...\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
