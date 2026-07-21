from fieldforge_contracts import EvaluationRun, GateDecision, GateMetricStatus
from fieldforge_ops_api.gate import compute_gate


def _run(metrics: dict, is_baseline: bool = False) -> EvaluationRun:
    return EvaluationRun(
        product="docs",
        dataset_id="docs_qa_v1",
        dataset_version="v1",
        case_count=20,
        metrics=metrics,
        is_baseline=is_baseline,
        source="test",
    )


def test_no_baseline_yields_no_baseline_decision():
    current = _run({"recall_at_5": 1.0})
    result = compute_gate(current, None)
    assert result.decision == GateDecision.NO_BASELINE
    assert result.comparisons[0].status == GateMetricStatus.MISSING


def test_identical_metrics_pass():
    baseline = _run({"recall_at_5": 1.0, "mrr": 0.9}, is_baseline=True)
    current = _run({"recall_at_5": 1.0, "mrr": 0.9})
    result = compute_gate(current, baseline)
    assert result.decision == GateDecision.PASS
    assert all(c.status == GateMetricStatus.PASS for c in result.comparisons)


def test_small_drop_within_epsilon_passes():
    baseline = _run({"recall_at_5": 1.0}, is_baseline=True)
    current = _run({"recall_at_5": 0.99})  # drop of 0.01, within 0.02 epsilon
    result = compute_gate(current, baseline)
    assert result.decision == GateDecision.PASS


def test_large_drop_fails():
    baseline = _run({"recall_at_5": 1.0}, is_baseline=True)
    current = _run({"recall_at_5": 0.5})
    result = compute_gate(current, baseline)
    assert result.decision == GateDecision.FAIL
    comparison = next(c for c in result.comparisons if c.metric_name == "recall_at_5")
    assert comparison.status == GateMetricStatus.FAIL
    assert comparison.delta == -0.5


def test_improvement_always_passes():
    baseline = _run({"recall_at_5": 0.8}, is_baseline=True)
    current = _run({"recall_at_5": 1.0})
    result = compute_gate(current, baseline)
    assert result.decision == GateDecision.PASS


def test_metric_missing_from_current_is_reported_not_blocking():
    baseline = _run({"recall_at_5": 1.0, "mrr": 0.9}, is_baseline=True)
    current = _run({"recall_at_5": 1.0})
    result = compute_gate(current, baseline)
    mrr_comparison = next(c for c in result.comparisons if c.metric_name == "mrr")
    assert mrr_comparison.status == GateMetricStatus.MISSING
    assert result.decision == GateDecision.PASS  # missing doesn't block


def test_non_numeric_metric_is_missing_not_blocking():
    baseline = _run({"faithfulness": "TBD"}, is_baseline=True)
    current = _run({"faithfulness": "TBD"})
    result = compute_gate(current, baseline)
    assert result.comparisons[0].status == GateMetricStatus.MISSING
    assert result.decision == GateDecision.PASS


def test_faster_latency_passes_not_flagged_as_regression():
    """Regression test for the real bug found during slice-1 testing: a faster
    (better) latency was incorrectly failing the gate — see ADR 0004 decision 1.
    """
    baseline = _run({"latency_ms_p50": 2.155}, is_baseline=True)
    current = _run({"latency_ms_p50": 1.982})  # faster than baseline
    result = compute_gate(current, baseline)
    assert result.decision == GateDecision.PASS
    assert result.comparisons[0].status == GateMetricStatus.PASS


def test_much_slower_latency_fails():
    baseline = _run({"latency_ms_p50": 2.0}, is_baseline=True)
    current = _run({"latency_ms_p50": 10.0})  # 5x slower, beyond the 50% tolerance
    result = compute_gate(current, baseline)
    assert result.decision == GateDecision.FAIL


def test_moderately_slower_latency_within_tolerance_passes():
    baseline = _run({"latency_ms_p50": 2.0}, is_baseline=True)
    current = _run({"latency_ms_p50": 2.8})  # 40% slower, within 50% tolerance
    result = compute_gate(current, baseline)
    assert result.decision == GateDecision.PASS
