"""Ask one question from the command line and see the answer, citations, cost and timing.

uv run python -m scripts.ask "What is the termination fee?" --deal juniper-hpe-2024
"""

import argparse
import io
import sys

from app.chains.answer import build_answer_chain_from_settings
from app.compat import use_selector_event_loop_on_windows
from app.config import get_settings
from app.retrieval.factory import build_retriever
from app.retrieval.hybrid import RetrievalConfig

use_selector_event_loop_on_windows()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question")
    parser.add_argument("--deal", action="append", required=True)
    parser.add_argument("--json", action="store_true", help="print the full JSON result")
    args = parser.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="replace")

    settings = get_settings()
    retriever = build_retriever(settings, config=RetrievalConfig(top_k=settings.top_k))
    chain = build_answer_chain_from_settings(settings, retriever)
    result = chain.invoke({"question": args.question, "deal_ids": args.deal})

    if args.json:
        print(result.model_dump_json(indent=2))
        return 0
    print(f"\n{result.answer}\n")
    for c in result.citations:
        print(f'  [{c.section_number}] "{c.quote}"   ({c.chunk_id})')
    print(f"\nreason: {result.reason}; rejected citations: {result.rejected_citations}")
    retrieved = [
        f"{s.section_number} ({s.rerank_score:.2f})"
        if s.rerank_score is not None
        else s.section_number
        for s in result.sources
    ]
    print("retrieved: " + ", ".join(retrieved))
    timing = ", ".join(f"{k} {v:.0f} ms" for k, v in result.timings_ms.items())
    print(
        f"tokens: {result.input_tokens:,} in / {result.output_tokens:,} out; "
        f"cost ${result.cost_usd:.4f}; {timing}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
