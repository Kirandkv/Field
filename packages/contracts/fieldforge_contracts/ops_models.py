"""Shared typed contracts for FieldForge Ops (milestone M5).

Ops doesn't generate new domain data — it ingests the real evaluation reports and
structured trace logs the other three products already produce (evals/reports/*.json,
JSON log lines with a trace_id) and enforces a quality gate against the baselines
already committed under evals/baselines/. See docs/adr/0004-ops-quality-gate.md.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid.uuid4().hex


class EvaluationRun(BaseModel):
    id: str = Field(default_factory=_new_id)
    product: str  # "docs" | "copilot" | "mesh"
    dataset_id: str
    dataset_version: str
    case_count: int
    metrics: dict[str, float | str]
    is_baseline: bool = False
    source: str  # which report file this was ingested from
    created_at: datetime = Field(default_factory=_utcnow)


class GateMetricStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    MISSING = "missing"  # metric present in one run but not the other


class MetricComparison(BaseModel):
    metric_name: str
    baseline_value: float | str | None
    current_value: float | str | None
    delta: float | None
    status: GateMetricStatus


class GateDecision(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NO_BASELINE = "no_baseline"


class QualityGateResult(BaseModel):
    id: str = Field(default_factory=_new_id)
    product: str
    dataset_id: str
    evaluation_run_id: str
    baseline_run_id: str | None
    decision: GateDecision
    comparisons: list[MetricComparison] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class TraceSpan(BaseModel):
    id: str = Field(default_factory=_new_id)
    trace_id: str
    service: str
    method: str | None = None
    path: str | None = None
    status_code: int | None = None
    duration_ms: float | None = None
    level: str = "INFO"
    message: str = ""
    timestamp: datetime = Field(default_factory=_utcnow)


class ReleaseStatus(StrEnum):
    ACTIVE = "active"
    ROLLED_BACK = "rolled_back"


class Release(BaseModel):
    id: str = Field(default_factory=_new_id)
    product: str
    environment: str  # "dev" | "staging" | "production"
    version_label: str
    evaluation_run_id: str
    status: ReleaseStatus = ReleaseStatus.ACTIVE
    canary_percent: float = 100.0
    created_at: datetime = Field(default_factory=_utcnow)


class RollbackEvent(BaseModel):
    id: str = Field(default_factory=_new_id)
    release_id: str
    previous_active_release_id: str | None
    reason: str
    triggered_by: str
    created_at: datetime = Field(default_factory=_utcnow)
