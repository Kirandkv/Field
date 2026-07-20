"""Reciprocal Rank Fusion (Cormack et al., 2009).

Slice 1 only ever has one ranked list (BM25) because the dense adapter defaults to
unavailable, so this is a documented no-op passthrough in that case. It exists now so
the retrieval call site never needs to change when a second (dense) ranked list ships.
"""

from __future__ import annotations

from fieldforge_contracts import RetrievalResult

RRF_K = 60  # standard constant from the RRF paper


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievalResult]], k: int = RRF_K
) -> list[RetrievalResult]:
    if len(ranked_lists) == 1:
        return ranked_lists[0]

    scores: dict[str, float] = {}
    best_result: dict[str, RetrievalResult] = {}
    for ranked in ranked_lists:
        for result in ranked:
            chunk_id = result.chunk.id
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + result.rank)
            best_result[chunk_id] = result

    fused_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    fused: list[RetrievalResult] = []
    for rank, chunk_id in enumerate(fused_ids, start=1):
        base = best_result[chunk_id]
        fused.append(
            RetrievalResult(
                chunk=base.chunk,
                score=scores[chunk_id],
                rank=rank,
                retriever="rrf",
            )
        )
    return fused
