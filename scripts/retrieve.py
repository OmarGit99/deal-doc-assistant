"""Run one question through retrieval and show what each stage found.

uv run python -m scripts.retrieve "What is the termination fee?" --deal juniper-hpe-2024
uv run python -m scripts.retrieve "What is the outside date?" --deal juniper-hpe-2024 --mode all
"""

import argparse
import io
import sys
from dataclasses import replace

from app.compat import use_selector_event_loop_on_windows
from app.config import get_settings
from app.retrieval.corpus import Candidate
from app.retrieval.factory import build_retriever
from app.retrieval.hybrid import MODES, Mode

use_selector_event_loop_on_windows()


def describe(rank: int, c: Candidate) -> list[str]:
    parts = []
    if c.rerank_score is not None:
        parts.append(f"rerank {c.rerank_score:.3f}")
    if c.fused_score:
        parts.append(f"rrf {c.fused_score:.4f}")
    parts.append(f"bm25 #{c.bm25_rank}" if c.bm25_rank else "bm25 -")
    parts.append(f"vector #{c.vector_rank}" if c.vector_rank else "vector -")
    body = c.body[:200].replace("\n", " / ")
    return [
        f"{rank}. {c.chunk_id}   [{', '.join(parts)}]",
        f"   {c.section_number} {c.section_title}",
        f"   {body}...",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question")
    parser.add_argument("--deal", action="append", default=[])
    parser.add_argument("--mode", choices=[*MODES, "all"], default="hybrid_rerank")
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="replace")

    retriever = build_retriever(get_settings())
    modes: list[Mode] = list(MODES) if args.mode == "all" else [args.mode]
    for mode in modes:
        config = replace(retriever.config, mode=mode, top_k=args.k)
        result = retriever.retrieve(args.question, args.deal or None, config)
        timing = ", ".join(f"{stage} {ms:.0f} ms" for stage, ms in result.timings_ms.items())
        print(f"\n=== {mode}   ({timing})")
        for rank, cand in enumerate(result.candidates, start=1):
            lines = describe(rank, cand)
            print("\n".join(lines if args.mode != "all" else lines[:2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
