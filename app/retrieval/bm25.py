"""Keyword search (BM25) over the chunks, with a deal filter."""

import math
import re
from collections.abc import Sequence
from dataclasses import replace

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from app.retrieval.corpus import Candidate

# Words, numbers and amounts: "termination", "11.04", "407,500,000", "40.00", "party's".
_TOKEN = re.compile(r"[a-z0-9]+(?:[.,'][a-z0-9]+)*")
# Very common words carry no signal. Legal words such as "shall" and "any" are kept out too.
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "such",
        "that",
        "the",
        "their",
        "there",
        "these",
        "this",
        "those",
        "to",
        "was",
        "were",
        "will",
        "with",
        "any",
        "shall",
        "all",
        "other",
        "which",
        "who",
    }  # fmt: skip
)


class _LuceneBM25(BM25Okapi):  # type: ignore[misc]  # rank_bm25 has no type hints
    """BM25Okapi with the IDF formula Lucene and Elasticsearch use.

    rank_bm25's default IDF, log((N - n + 0.5) / (n + 0.5)), is zero for a word found in
    exactly half the chunks and negative above that (it then substitutes a small constant).
    Common contract words such as "termination" or "fee" would count for almost nothing.
    log(1 + ...) is always positive and only shrinks as a word gets more common.
    """

    def _calc_idf(self, nd: dict[str, int]) -> None:
        for word, freq in nd.items():
            self.idf[word] = math.log(1 + (self.corpus_size - freq + 0.5) / (freq + 0.5))


def tokenize(text: str) -> list[str]:
    tokens = _TOKEN.findall(text.lower())
    # Single letters are mostly subsection labels such as the "b" in 11.04(b).
    return [t for t in tokens if t not in STOPWORDS and (len(t) > 1 or t.isdigit())]


class BM25Index:
    """One index over every deal's chunks.

    A single index keeps the inverse document frequencies (how rare a word is) measured
    over the whole corpus. Filtering by deal happens after scoring, which is cheap: about
    5,000 chunks score in a few milliseconds.
    """

    def __init__(self, chunks: Sequence[Candidate]) -> None:
        if not chunks:
            raise ValueError("cannot build a BM25 index from zero chunks")
        self.chunks = list(chunks)
        self._bm25 = _LuceneBM25([tokenize(c.text) for c in self.chunks])
        self._by_deal: dict[str, list[int]] = {}
        for i, chunk in enumerate(self.chunks):
            self._by_deal.setdefault(chunk.deal_id, []).append(i)

    @property
    def deal_ids(self) -> set[str]:
        return set(self._by_deal)

    def search(self, query: str, deal_ids: Sequence[str] | None, k: int) -> list[Candidate]:
        scores = self._bm25.get_scores(tokenize(query))
        if deal_ids:
            pool = [i for d in deal_ids for i in self._by_deal.get(d, [])]
        else:
            pool = list(range(len(self.chunks)))
        ranked = sorted((i for i in pool if scores[i] > 0), key=lambda i: -scores[i])[:k]
        return [
            replace(self.chunks[i], bm25_rank=rank, bm25_score=float(scores[i]))
            for rank, i in enumerate(ranked, start=1)
        ]
