"""Check the golden set against the downloaded agreements.

Run after scripts.download:
    uv run python -m evals.check_golden
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.ingest.edgar import SeedError, cached_exhibit_path, load_seed
from app.text import contains_quote, decode_html, normalize, strip_html


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deal_id: str | None = None  # required when the item covers more than one deal
    section: str
    quote: str = Field(min_length=1)


class GoldenItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    type: Literal["answerable", "definition", "unanswerable", "comparison"]
    phrasing: Literal["analyst", "formal"] | None = None
    deal_ids: list[str] = Field(min_length=1)
    question: str = Field(min_length=1)
    sections: list[str]
    key_facts: list[str]
    reference_answer: str = Field(min_length=1)
    evidence: list[Evidence]

    @model_validator(mode="after")
    def _shape_matches_type(self) -> Self:
        if self.type == "unanswerable" and self.sections:
            raise ValueError("unanswerable items must have no sections")
        if self.type != "unanswerable" and not self.sections:
            raise ValueError("answerable items need at least one section")
        if self.type == "comparison" and len(self.deal_ids) != 2:
            raise ValueError("comparison items need exactly two deal_ids")
        if len(self.deal_ids) > 1 and any(e.deal_id is None for e in self.evidence):
            raise ValueError("multi-deal items must set deal_id on every evidence entry")
        return self


def load_golden(path: Path) -> tuple[list[GoldenItem], list[str]]:
    items: list[GoldenItem] = []
    problems: list[str] = []
    seen: set[str] = set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = GoldenItem.model_validate(json.loads(line))
        except (json.JSONDecodeError, ValidationError) as exc:
            problems.append(f"line {line_no}: {exc}")
            continue
        if item.id in seen:
            problems.append(f"line {line_no}: duplicate id {item.id}")
        seen.add(item.id)
        items.append(item)
    return items, problems


def check_item(item: GoldenItem, texts: dict[str, str]) -> list[str]:
    problems: list[str] = []
    answer = normalize(item.reference_answer)
    evidence_text = " ".join(e.quote for e in item.evidence)
    for fact in item.key_facts:
        if normalize(fact) not in answer:
            problems.append(f"{item.id}: key fact {fact!r} is missing from reference_answer")
        if not contains_quote(evidence_text, fact):
            problems.append(f"{item.id}: key fact {fact!r} is not in any evidence quote")

    for ev in item.evidence:
        deal_id = ev.deal_id or item.deal_ids[0]
        if deal_id not in texts:
            problems.append(f"{item.id}: {deal_id} is not downloaded (or not in the seed file)")
        elif "..." in ev.quote or "…" in ev.quote:
            problems.append(f"{item.id}: quote for {ev.section} contains '...'; split it")
        elif not contains_quote(texts[deal_id], ev.quote):
            preview = normalize(ev.quote)[:70]
            problems.append(f"{item.id}: {ev.section} quote not in {deal_id}: {preview!r}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--golden", type=Path, default=Path("evals/golden_set.jsonl"))
    parser.add_argument("--seed", type=Path, default=Path("scripts/seed_deals.csv"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    args = parser.parse_args(argv)

    try:
        deals = load_seed(args.seed)
    except SeedError as exc:
        print(f"Seed file has problems:\n{exc}", file=sys.stderr)
        return 2

    texts: dict[str, str] = {}
    for deal in deals:
        path = cached_exhibit_path(deal, args.raw_dir)
        if path.exists():
            texts[deal.deal_id] = strip_html(decode_html(path.read_bytes()))

    items, problems = load_golden(args.golden)
    for item in items:
        problems.extend(check_item(item, texts))

    counts: dict[str, int] = {}
    for item in items:
        counts[item.type] = counts.get(item.type, 0) + 1
    summary = ", ".join(f"{n} {kind}" for kind, n in sorted(counts.items()))
    print(f"{len(items)} items ({summary})")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("All quotes and key facts check out.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
