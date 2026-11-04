"""Parse every downloaded agreement and report the structure found.

uv run python -m scripts.inspect_sections                    # summary table
uv run python -m scripts.inspect_sections --deal pioneer-exxon-2023   # full outline
uv run python -m scripts.inspect_sections --dump             # also write data/parsed/*.json
"""

import argparse
import io
import json
import sys
from dataclasses import asdict
from pathlib import Path

from app.ingest.edgar import SeedError, cached_exhibit_path, load_seed
from app.ingest.parse import html_to_lines
from app.ingest.sections import ANNEX_ARTICLE, ParsedAgreement, parse_structure
from app.text import decode_html


def outline(parsed: ParsedAgreement) -> str:
    out = [f"{parsed.deal_id}  (body start: {parsed.body_start_method})", ""]
    out.append(f"PREAMBLE  {len(parsed.preamble):,} chars")
    groups = [(f"{a.word} {a.label}  {a.title}", a.number) for a in parsed.articles]
    groups.append(("ANNEXES (after the signature pages)", ANNEX_ARTICLE))
    for heading, number in groups:
        members = [s for s in parsed.sections if s.article_number == number]
        if number == ANNEX_ARTICLE and not members:
            continue
        out.append(heading)
        for s in members:
            terms = f"  [{len(s.defined_terms)} terms]" if s.defined_terms else ""
            out.append(f"    {s.number:<9} {s.title[:58]:<58} {len(s.text):>7,} chars{terms}")
    for dropped in parsed.dropped_annexes:
        out.append(f"dropped: {dropped}")
    out.append("")
    out.append(f"{len(parsed.definitions)} definitions, {len(parsed.term_index)} index entries")
    out.append(f"{parsed.trailing_chars:,} chars dropped after the signature block")
    for warning in parsed.warnings:
        out.append(f"WARNING: {warning}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=Path, default=Path("scripts/seed_deals.csv"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--deal", action="append", default=[], help="print a full outline")
    parser.add_argument("--dump", action="store_true", help="write data/parsed/{deal_id}.json")
    parser.add_argument(
        "--warnings", action="store_true", help="list warnings and dropped annexes for every deal"
    )
    args = parser.parse_args(argv)
    # Redirected output on Windows defaults to cp1252; never crash on an odd character.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="replace")

    try:
        deals = load_seed(args.seed)
    except SeedError as exc:
        print(f"Seed file has problems:\n{exc}", file=sys.stderr)
        return 2

    if args.deal:
        deals = [d for d in deals if d.deal_id in args.deal]

    header = (
        f"{'deal_id':<38} {'start':<9} {'art':>3} {'sec':>4} {'anx':>3} {'defs':>5} "
        f"{'idx':>4} {'dropped':>8}  warn"
    )
    if not args.deal and not args.warnings:
        print(header)
        print("-" * len(header))
    for deal in deals:
        path = cached_exhibit_path(deal, args.raw_dir)
        if not path.exists():
            print(f"{deal.deal_id:<38} not downloaded")
            continue
        parsed = parse_structure(html_to_lines(decode_html(path.read_bytes())), deal.deal_id)
        if args.dump:
            out = Path("data/parsed") / f"{deal.deal_id}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(asdict(parsed), indent=2, ensure_ascii=False), "utf-8")
        if args.warnings:
            notes = [f"WARNING: {w}" for w in parsed.warnings]
            notes += [f"dropped: {d}" for d in parsed.dropped_annexes]
            if notes:
                print(f"\n{deal.deal_id}")
                print("\n".join(f"  {n}" for n in notes))
            continue
        if args.deal:
            print(outline(parsed), end="\n\n")
        else:
            annexes = sum(s.article_number == ANNEX_ARTICLE for s in parsed.sections)
            print(
                f"{deal.deal_id:<38} {parsed.body_start_method:<9} {len(parsed.articles):>3} "
                f"{len(parsed.sections) - annexes:>4} {annexes:>3} {len(parsed.definitions):>5} "
                f"{len(parsed.term_index):>4} {parsed.trailing_chars:>8,}  {len(parsed.warnings)}"
            )
    if not args.deal and not args.warnings:
        print("\nRun with --deal <deal_id> to see the outline and warnings for one deal.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
