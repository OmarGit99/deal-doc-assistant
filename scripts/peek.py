"""Print small excerpts of parsed agreement lines, for debugging the parser.

    uv run python -m scripts.peek DEAL_ID "regex" [--before 1] [--after 3] [--max 5]
    uv run python -m scripts.peek --diagnose > diagnose.txt

Lines are the output of html_to_lines, so you see exactly what the parser sees.
Long lines are clipped to keep the output small.
"""

import argparse
import io
import re
import sys
from collections import Counter
from pathlib import Path

from app.ingest.edgar import SeedError, cached_exhibit_path, load_seed
from app.ingest.parse import find_body_end, find_body_start, html_to_lines
from app.text import decode_html

WIDTH = 140

# (deal_id, pattern, lines before, lines after, max matches, what we are checking)
DIAGNOSE: list[tuple[str, str, int, int, int, str]] = [
    ("ansys-synopsys-2024", r"^(?:section\s+)?1\.0?1\b", 4, 2, 3, "what comes before 1.1"),
    ("ansys-synopsys-2024", r"^(?:section\s+)?8\.0?1\b", 4, 1, 2, "what comes before 8.1"),
    ("wbd-paramount-skydance-2026", r"^", 0, 0, 3, "first lines"),
    ("everbridge-thomabravo-2024", r"follow|witness|executed|signature", 1, 1, 5, "end of body"),
    ("everbridge-thomabravo-2024", r"^(?:annex|exhibit)\b", 0, 1, 6, "what is after"),
    ("hashicorp-ibm-2024", r'"\s+(?:shall\s+)?(?:means|has the meaning)', 0, 0, 4, "definitions"),
    ("hashicorp-ibm-2024", r"^(?:section\s+)?1\.0?1\b", 2, 2, 2, "first section"),
    ("kellanova-mars-2024", r"1,250,000,000", 2, 1, 3, "buyer fee"),
]
# Deals whose raw HTML structure is printed (tag counts, longest lines).
DIAGNOSE_HTML = ["wbd-paramount-skydance-2026", "ansys-synopsys-2024"]


def html_summary(markup: str, lines: list[str]) -> list[str]:
    tags = Counter(m.lower() for m in re.findall(r"<([a-zA-Z][a-zA-Z0-9]*)", markup))
    out = ["  tags: " + ", ".join(f"{t}={n}" for t, n in tags.most_common(12))]
    out.append(f"  {len(markup):,} chars of HTML -> {len(lines):,} lines")
    for line in sorted(lines, key=len, reverse=True)[:3]:
        out.append(f"  longest: {_clip(line)}")
    body = markup.lower().find("<body")
    sample = re.sub(r"\s+", " ", markup[body : body + 600] if body >= 0 else markup[:600])
    out.append(f"  html: {sample}")
    return out


def _clip(line: str) -> str:
    return line if len(line) <= WIDTH else f"{line[:WIDTH]}... [{len(line):,} chars]"


def peek(lines: list[str], pattern: str, before: int, after: int, max_matches: int) -> list[str]:
    regex = re.compile(pattern, re.IGNORECASE)
    out: list[str] = []
    count = 0
    for i, line in enumerate(lines):
        if not regex.search(line):
            continue
        count += 1
        if count > max_matches:
            continue
        out.append(f"  -- match {count}")
        for j in range(max(0, i - before), min(len(lines), i + after + 1)):
            out.append(f"  {'>' if j == i else ' '}{j:>6}  {_clip(lines[j])}")
    out.append(f"  ({count} matches in total)")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("deal_id", nargs="?")
    parser.add_argument("pattern", nargs="?")
    parser.add_argument("--before", type=int, default=1)
    parser.add_argument("--after", type=int, default=3)
    parser.add_argument("--max", type=int, default=5)
    parser.add_argument("--diagnose", action="store_true", help="run the built-in checks")
    parser.add_argument("--seed", type=Path, default=Path("scripts/seed_deals.csv"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    args = parser.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="replace")

    if args.diagnose:
        probes = DIAGNOSE
    elif args.deal_id and args.pattern:
        probes = [(args.deal_id, args.pattern, args.before, args.after, args.max, "")]
    else:
        parser.error("give DEAL_ID and PATTERN, or --diagnose")

    try:
        deals = {d.deal_id: d for d in load_seed(args.seed)}
    except SeedError as exc:
        print(f"Seed file has problems:\n{exc}", file=sys.stderr)
        return 2

    if args.diagnose:
        for deal_id in DIAGNOSE_HTML:
            deal = deals.get(deal_id)
            if deal is None or not cached_exhibit_path(deal, args.raw_dir).exists():
                continue
            markup = decode_html(cached_exhibit_path(deal, args.raw_dir).read_bytes())
            print(f"\n== {deal_id}  raw HTML")
            print("\n".join(html_summary(markup, html_to_lines(markup))))

    cache: dict[str, list[str]] = {}
    for deal_id, pattern, before, after, max_matches, purpose in probes:
        deal = deals.get(deal_id)
        if deal is None or not cached_exhibit_path(deal, args.raw_dir).exists():
            print(f"\n== {deal_id}: not downloaded")
            continue
        if deal_id not in cache:
            raw = cached_exhibit_path(deal, args.raw_dir).read_bytes()
            cache[deal_id] = html_to_lines(decode_html(raw))
        lines = cache[deal_id]
        start, method = find_body_start(lines)
        end, _ = find_body_end(lines, start)
        print(f"\n== {deal_id}  /{pattern}/  {purpose}")
        print(f"   {len(lines):,} lines; body {start}-{end} (start by {method})")
        print("\n".join(peek(lines, pattern, before, after, max_matches)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
