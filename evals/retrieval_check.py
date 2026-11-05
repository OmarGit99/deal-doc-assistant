"""Retrieval hit rate on the golden set, for every retrieval mode. Runs locally, no LangSmith.

    uv run python -m evals.retrieval_check
    uv run python -m evals.retrieval_check --mode hybrid_rerank --show-misses

For each question it retrieves the top k chunks (inside the question's deal) and checks
whether the reference sections are among them:
  hit@k (any)  at least one reference section was retrieved
  hit@k (all)  every reference section was retrieved (matters for multi-section answers)
  MRR          1 / rank of the first correct chunk, averaged; rewards ranking it high
"""

import argparse
import io
import statistics
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from app.compat import use_selector_event_loop_on_windows
from app.config import get_settings
from app.ingest.sections import section_matches
from app.retrieval.corpus import Candidate
from app.retrieval.factory import build_retriever
from app.retrieval.hybrid import MODES, HybridRetriever, Mode
from evals.check_golden import GoldenItem, load_golden

use_selector_event_loop_on_windows()


@dataclass
class Outcome:
    item_id: str
    deal_id: str
    expected: list[str]
    got: list[str]
    hit_any: bool
    hit_all: bool
    reciprocal_rank: float
    best_rerank: float | None


def expected_by_deal(item: GoldenItem) -> dict[str, list[str]]:
    """Reference sections per deal. Comparison items say which deal each quote is from."""
    if len(item.deal_ids) == 1:
        return {item.deal_ids[0]: item.sections}
    grouped: dict[str, list[str]] = {d: [] for d in item.deal_ids}
    for ev in item.evidence:
        if ev.deal_id in grouped and ev.section not in grouped[ev.deal_id]:
            grouped[ev.deal_id].append(ev.section)
    return grouped


def score(item_id: str, deal_id: str, expected: list[str], got: list[Candidate]) -> Outcome:
    found = [any(section_matches(ref, c.section_number) for c in got) for ref in expected]
    first = next(
        (
            rank
            for rank, c in enumerate(got, 1)
            if any(section_matches(r, c.section_number) for r in expected)
        ),
        None,
    )
    rerank = [c.rerank_score for c in got if c.rerank_score is not None]
    return Outcome(
        item_id,
        deal_id,
        expected,
        [c.section_number for c in got],
        any(found),
        all(found),
        1 / first if first else 0.0,
        max(rerank) if rerank else None,
    )


def run(retriever: HybridRetriever, items: list[GoldenItem], mode: Mode, k: int) -> list[Outcome]:
    config = replace(retriever.config, mode=mode, top_k=k)
    outcomes = []
    for item in items:
        for deal_id, expected in expected_by_deal(item).items():
            got = retriever.retrieve(item.question, [deal_id], config).candidates
            outcomes.append(score(item.id, deal_id, expected, got))
    return outcomes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--golden", type=Path, default=Path("evals/golden_set.jsonl"))
    parser.add_argument("--mode", choices=[*MODES, "all"], default="all")
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument("--show-misses", action="store_true")
    args = parser.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="replace")

    items, problems = load_golden(args.golden)
    if problems:
        print("Golden set has problems; run evals.check_golden first.", file=sys.stderr)
        return 2
    answerable = [i for i in items if i.type != "unanswerable"]
    unanswerable = [i for i in items if i.type == "unanswerable"]

    retriever = build_retriever(get_settings())
    modes: list[Mode] = list(MODES) if args.mode == "all" else [args.mode]
    print(f"{len(answerable)} answerable questions, top {args.k}\n")
    print(f"{'mode':<15} {'hit (any)':>9} {'hit (all)':>9} {'MRR':>6}")
    misses: dict[Mode, list[Outcome]] = {}
    for mode in modes:
        outcomes = run(retriever, answerable, mode, args.k)
        n = len(outcomes)
        print(
            f"{mode:<15} {sum(o.hit_any for o in outcomes) / n:>9.0%} "
            f"{sum(o.hit_all for o in outcomes) / n:>9.0%} "
            f"{statistics.mean(o.reciprocal_rank for o in outcomes):>6.2f}"
        )
        misses[mode] = [o for o in outcomes if not o.hit_all]

    if args.show_misses:
        for mode, missed in misses.items():
            print(f"\nMisses ({mode}):")
            for o in missed:
                print(f"  {o.item_id} {o.deal_id}: expected {o.expected}, got {o.got}")

    if "hybrid_rerank" in modes:
        # Preview of the "not found" gate: best rerank score for questions the agreement
        # answers versus questions it does not. The threshold is set from these in Week 3.
        best = [o.best_rerank for o in run(retriever, answerable, "hybrid_rerank", args.k)]
        none = [o.best_rerank for o in run(retriever, unanswerable, "hybrid_rerank", args.k)]
        known = sorted(s for s in best if s is not None)
        print("\nBest rerank score per question (for the not-found threshold):")
        if known:
            print(f"  answerable:   min {known[0]:.3f}, median {statistics.median(known):.3f}")
        print(f"  unanswerable: {', '.join(f'{s:.3f}' for s in none if s is not None) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
