"""Quality-gate comparison logic — pure functions, no I/O, so the policy itself is
directly unit-testable independent of the API/store. See
docs/adr/0004-ops-quality-gate.md decision 1 for the threshold policy.
"""

from __future__ import annotations

from fieldforge_contracts import (
    EvaluationRun,
    GateDecision,
    GateMetricStatus,
    MetricComparison,
    QualityGateResult,
)

REGRESSION_EPSILON = 0.02  # absolute tolerance for higher-is-better rate/score metrics
LATENCY_TOLERANCE_PCT = 0.5  # 50% — local eval runs have real run-to-run jitter


def _is_lower_better(name: str) -> bool:
    """Latency metrics regress by going up, not down — found as a real bug during
    slice-1 testing: the first version of this function didn't exist, and a faster
    (better) latency_ms_p50 was flagged as a failing regression because the
    higher-is-better comparison ran on it unconditionally. See ADR 0004.
    """
    return "latency" in name.lower()


def _compare_one(name: str, baseline_value, current_value) -> MetricComparison:
    if baseline_value is None or current_value is None:
        return MetricComparison(
            metric_name=name,
            baseline_value=baseline_value,
            current_value=current_value,
            delta=None,
            status=GateMetricStatus.MISSING,
        )
    if not isinstance(baseline_value, int | float) or not isinstance(current_value, int | float):
        # Non-numeric values (e.g. "TBD") can't be gated — reported, not blocking.
        return MetricComparison(
            metric_name=name,
            baseline_value=baseline_value,
            current_value=current_value,
            delta=None,
            status=GateMetricStatus.MISSING,
        )

    delta = current_value - baseline_value
    if _is_lower_better(name):
        passed = current_value <= baseline_value * (1 + LATENCY_TOLERANCE_PCT)
    else:
        passed = current_value >= baseline_value - REGRESSION_EPSILON
    status = GateMetricStatus.PASS if passed else GateMetricStatus.FAIL

    return MetricComparison(
        metric_name=name,
        baseline_value=baseline_value,
        current_value=current_value,
        delta=round(delta, 4),
        status=status,
    )


def compute_gate(current: EvaluationRun, baseline: EvaluationRun | None) -> QualityGateResult:
    if baseline is None:
        return QualityGateResult(
            product=current.product,
            dataset_id=current.dataset_id,
            evaluation_run_id=current.id,
            baseline_run_id=None,
            decision=GateDecision.NO_BASELINE,
            comparisons=[
                MetricComparison(
                    metric_name=k,
                    baseline_value=None,
                    current_value=v,
                    delta=None,
                    status=GateMetricStatus.MISSING,
                )
                for k, v in current.metrics.items()
            ],
        )

    metric_names = sorted(set(current.metrics) | set(baseline.metrics))
    comparisons = [
        _compare_one(name, baseline.metrics.get(name), current.metrics.get(name)) for name in metric_names
    ]
    any_failed = any(c.status == GateMetricStatus.FAIL for c in comparisons)
    decision = GateDecision.FAIL if any_failed else GateDecision.PASS

    return QualityGateResult(
        product=current.product,
        dataset_id=current.dataset_id,
        evaluation_run_id=current.id,
        baseline_run_id=baseline.id,
        decision=decision,
        comparisons=comparisons,
    )
