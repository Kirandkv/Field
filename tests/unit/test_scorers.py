from scorers.retrieval_scorer import (
    CaseResult,
    citation_correctness,
    mean_reciprocal_rank,
    recall_at_k,
    refusal_accuracy,
)


def _case(gold, retrieved, expect_refusal=False, actual_refused=False, citations_valid=True):
    return CaseResult(
        case_id="c",
        gold_filenames=set(gold),
        retrieved_filenames=retrieved,
        expect_refusal=expect_refusal,
        actual_refused=actual_refused,
        citations_valid=citations_valid,
        latency_ms=1.0,
    )


def test_recall_at_k_counts_hit_when_gold_in_retrieved():
    results = [_case(["a.md"], ["b.md", "a.md"]), _case(["c.md"], ["d.md"])]
    assert recall_at_k(results) == 0.5


def test_recall_at_k_ignores_cases_with_no_gold_filenames():
    results = [_case([], ["a.md"])]
    assert recall_at_k(results) == 0.0


def test_mrr_rewards_earlier_rank():
    first_rank = _case(["a.md"], ["a.md", "b.md"])
    second_rank = _case(["b.md"], ["a.md", "b.md"])
    assert mean_reciprocal_rank([first_rank]) == 1.0
    assert mean_reciprocal_rank([second_rank]) == 0.5


def test_refusal_accuracy_matches_expected_vs_actual():
    correct = _case([], [], expect_refusal=True, actual_refused=True)
    wrong = _case([], [], expect_refusal=True, actual_refused=False)
    assert refusal_accuracy([correct, wrong]) == 0.5


def test_citation_correctness_only_counts_non_refused_cases():
    refused = _case([], [], actual_refused=True, citations_valid=False)
    valid = _case(["a.md"], ["a.md"], citations_valid=True)
    assert citation_correctness([refused, valid]) == 1.0
