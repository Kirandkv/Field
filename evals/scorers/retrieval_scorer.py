"""Retrieval and answer-quality scorers for FieldForge Docs eval datasets.

Pure functions, no framework dependency, so they're independently unit-testable
(see tests/unit/test_scorers.py) and reusable from scripts/run_eval.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from fieldforge_contracts import RetrievalResult


@dataclass
class CaseResult:
    case_id: str
    gold_filenames: set[str]
    retrieved_filenames: list[str]  # ranked, best first
    expect_refusal: bool
    actual_refused: bool
    citations_valid: bool
    latency_ms: float


def recall_at_k(results: list[CaseResult]) -> float:
    scored = [r for r in results if r.gold_filenames]
    if not scored:
        return 0.0
    hits = sum(1 for r in scored if r.gold_filenames & set(r.retrieved_filenames))
    return hits / len(scored)


def mean_reciprocal_rank(results: list[CaseResult]) -> float:
    scored = [r for r in results if r.gold_filenames]
    if not scored:
        return 0.0
    total = 0.0
    for r in scored:
        rank = next(
            (i + 1 for i, fn in enumerate(r.retrieved_filenames) if fn in r.gold_filenames), None
        )
        if rank is not None:
            total += 1.0 / rank
    return total / len(scored)


def refusal_accuracy(results: list[CaseResult]) -> float:
    if not results:
        return 0.0
    correct = sum(1 for r in results if r.expect_refusal == r.actual_refused)
    return correct / len(results)


def citation_correctness(results: list[CaseResult]) -> float:
    non_refused = [r for r in results if not r.actual_refused]
    if not non_refused:
        return 0.0
    correct = sum(1 for r in non_refused if r.citations_valid)
    return correct / len(non_refused)


def latency_percentile(results: list[CaseResult], pct: float) -> float:
    if not results:
        return 0.0
    values = sorted(r.latency_ms for r in results)
    idx = min(len(values) - 1, int(round(pct / 100 * (len(values) - 1))))
    return values[idx]


def retrieved_filenames(
    results: list[RetrievalResult], doc_id_to_filename: dict[str, str]
) -> list[str]:
    return [doc_id_to_filename.get(r.chunk.document_id, r.chunk.document_id) for r in results]
