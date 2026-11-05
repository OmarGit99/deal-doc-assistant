"""Cross-encoder reranking.

A cross-encoder reads the question and one passage together and scores how well the
passage answers it. That is slower than comparing two precomputed vectors, but much more
accurate, so it runs only on the ~20 candidates the first stage found.
"""

from pathlib import Path
from typing import Any, Protocol


class Reranker(Protocol):
    def score(self, query: str, texts: list[str]) -> list[float]:
        """One relevance score per text, in the same order. Higher is better."""
        ...


class FlashRankReranker:
    """FlashRank's ONNX cross-encoders run on CPU with no PyTorch install.

    The model downloads on first use (about 34 MB for MiniLM-L-12) into `cache_dir`.
    Scores are between 0 and 1, which makes them usable for the "not found" threshold.
    """

    def __init__(
        self,
        model_name: str = "ms-marco-MiniLM-L-12-v2",
        cache_dir: Path = Path("data/models"),
        max_length: int = 512,
    ) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.max_length = max_length  # tokens; longer passages are cut off at this length
        self._ranker: Any = None

    def _load(self) -> Any:
        if self._ranker is None:
            from flashrank import Ranker  # type: ignore[import-untyped]

            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._ranker = Ranker(
                model_name=self.model_name,
                cache_dir=str(self.cache_dir),
                max_length=self.max_length,
                # FlashRank's default "INFO" switches on INFO logging for every library,
                # which floods the console with one httpx line per API call.
                log_level="WARNING",
            )
        return self._ranker

    def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        from flashrank import RerankRequest

        passages = [{"id": i, "text": t} for i, t in enumerate(texts)]
        results = self._load().rerank(RerankRequest(query=query, passages=passages))
        by_id = {int(r["id"]): float(r["score"]) for r in results}
        return [by_id[i] for i in range(len(texts))]
