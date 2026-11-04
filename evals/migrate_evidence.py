"""One-off: convert string `evidence` fields to the list-of-objects format.

    uv run python -m evals.migrate_evidence evals/golden_set.jsonl

Rewrites the file in place (keep it in git so you can diff the result). Safe to re-run:
items that already have a list are left alone.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

# Comparison items were written as: deal-id 8.5(d): "quote" | other-deal 6.03(a): "quote"
_COMPARISON_PART = re.compile(
    r'^(?P<deal>[a-z0-9-]+) (?P<section>\S+): "(?P<quote>.*)"$', re.DOTALL
)


def migrate(item: dict[str, Any]) -> dict[str, Any]:
    evidence = item.get("evidence")
    if not isinstance(evidence, str):
        return item
    sections: list[str] = item.get("sections") or [""]
    entries: list[dict[str, str]] = []

    if len(item["deal_ids"]) > 1:
        for part in evidence.split(" | "):
            match = _COMPARISON_PART.match(part.strip())
            if not match:
                raise ValueError(f"{item['id']}: cannot parse comparison evidence {part[:60]!r}")
            entries.append(
                {"deal_id": match["deal"], "section": match["section"], "quote": match["quote"]}
            )
    else:
        parts = [p.strip() for p in evidence.split(" ... ")]
        for index, quote in enumerate(parts):
            # Pair the n-th quote with the n-th section; extra quotes reuse the last one.
            section = sections[min(index, len(sections) - 1)]
            entries.append({"section": section, "quote": quote})

    return {**item, "evidence": entries}


def main(path: Path) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    items = [migrate(json.loads(line)) for line in lines if line.strip()]
    path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items), encoding="utf-8"
    )
    print(f"Migrated {len(items)} items in {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "evals/golden_set.jsonl")))
