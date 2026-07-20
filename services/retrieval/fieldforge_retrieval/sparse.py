"""BM25 sparse retrieval — the default, always-available retriever for slice 1.

Deterministic, no external service, no network call. See docs/architecture/OVERVIEW.md
for why this is the slice-1 default instead of dense/hybrid retrieval.
"""

from __future__ import annotations

from fieldforge_contracts import Chunk, RetrievalResult
from rank_bm25 import BM25Okapi


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


class BM25Index:
    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._bm25: BM25Okapi | None = None

    def build(self, chunks: list[Chunk]) -> None:
        self._chunks = list(chunks)
        corpus = [_tokenize(c.text) for c in self._chunks]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    @property
    def size(self) -> int:
        return len(self._chunks)

    def search(self, query: str, k: int = 5) -> list[RetrievalResult]:
        if self._bm25 is None or not self._chunks:
            return []

        query_tokens = _tokenize(query)
        # Whether any query term exists in the corpus vocabulary at all. This — not
        # the BM25 score's sign or magnitude — is the correct "no evidence" signal.
        # Okapi BM25's un-smoothed IDF (log(N-n+0.5) - log(n+0.5), no +1 term) can
        # land on exactly 0.0 or go negative for terms that appear in most/all
        # documents, which happens routinely in small corpora (e.g. a term present
        # in exactly 1 of 2 documents can coincidentally score idf==0.0). That is a
        # property of the corpus size, not evidence the term is absent, so a
        # score-based cutoff was previously (incorrectly) dropping real matches in
        # small corpora. See tests/unit/test_retrieval.py for the regression this
        # vocabulary check guards against.
        if not any(t in self._bm25.idf for t in query_tokens):
            return []

        scores = self._bm25.get_scores(query_tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [
            RetrievalResult(
                chunk=self._chunks[idx], score=float(scores[idx]), rank=rank, retriever="bm25"
            )
            for rank, idx in enumerate(ranked, start=1)
        ]
