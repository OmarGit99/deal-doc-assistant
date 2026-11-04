"""Download every exhibit in the seed CSV into data/raw/.

Run from the repo root:
    uv run --env-file .env python -m scripts.download
    uv run --env-file .env python -m scripts.download --only kellanova-mars-2024 --force
"""

import argparse
import sys
import time
from pathlib import Path

from app.ingest.edgar import (
    ExhibitError,
    FetchResult,
    SeedError,
    build_client,
    fetch_exhibit,
    load_seed,
    user_agent_from_env,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=Path, default=Path("scripts/seed_deals.csv"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--only", action="append", default=[], help="deal_id (repeatable)")
    parser.add_argument("--force", action="store_true", help="re-download even if cached")
    parser.add_argument("--delay", type=float, default=0.5, help="seconds between requests")
    args = parser.parse_args(argv)

    try:
        deals = load_seed(args.seed)
    except SeedError as exc:
        print(f"Seed file has problems:\n{exc}", file=sys.stderr)
        return 2

    if args.only:
        unknown = set(args.only) - {d.deal_id for d in deals}
        if unknown:
            print(f"Unknown deal_id(s): {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
        deals = [d for d in deals if d.deal_id in args.only]

    try:
        user_agent = user_agent_from_env()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 2

    results: list[FetchResult] = []
    failures: list[ExhibitError] = []
    with build_client(user_agent) as client:
        for deal in deals:
            try:
                result = fetch_exhibit(client, deal, args.raw_dir, force=args.force)
            except ExhibitError as exc:
                failures.append(exc)
                print(f"  FAIL    {deal.deal_id}")
                time.sleep(args.delay)
                continue
            results.append(result)
            print(f"  {'fetched' if result.downloaded else 'cached ':7} {deal.deal_id}")
            if result.downloaded:
                time.sleep(args.delay)  # only pause after a real request

    fetched = sum(r.downloaded for r in results)
    print(
        f"\n{len(deals)} deals: {fetched} downloaded, {len(results) - fetched} from cache, "
        f"{len(failures)} failed"
    )
    for failure in failures:
        print(f"  - {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
