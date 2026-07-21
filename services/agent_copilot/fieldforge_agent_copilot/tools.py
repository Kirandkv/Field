"""Copilot's read-only investigation tools.

Every tool returns a ToolResult (never raises to its caller) so the orchestrator can
make state-machine decisions on failure without a try/except per call site. Only
`draft_maintenance_ticket` here is preparatory (produces a ProposedAction, writes
nothing) — the state-changing counterpart, `create_maintenance_ticket`, lives in
apps/copilot_api because it only ever runs after a human approval decision reaches
the API layer; see ADR 0002 decision 3.
"""

from __future__ import annotations

import time
from datetime import datetime

import httpx
from fieldforge_anomaly import DeviceAnomalyDetector
from fieldforge_contracts import (
    Device,
    ProposedAction,
    RiskLevel,
    TelemetryPoint,
    ToolResult,
    ToolStatus,
)
from fieldforge_telemetry import TelemetryStore

DEFAULT_DOCS_API_URL = "http://localhost:8000"
DEFAULT_HTTP_TIMEOUT_SECONDS = 5.0


def _timed(fn):
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = fn(*args, **kwargs)
        result.duration_ms = round((time.perf_counter() - start) * 1000, 3)
        return result

    return wrapper


@_timed
def get_device(store: TelemetryStore, device_id: str) -> ToolResult:
    device: Device | None = store.get_device(device_id)
    if device is None:
        return ToolResult(
            tool_name="get_device", status=ToolStatus.ERROR, ok=False, error=f"unknown device {device_id!r}"
        )
    return ToolResult(
        tool_name="get_device", status=ToolStatus.SUCCESS, ok=True, data=device.model_dump(mode="json")
    )


@_timed
def get_sensor_history(
    store: TelemetryStore, device_id: str, center: datetime, half_width_seconds: float
) -> ToolResult:
    points = store.get_window(device_id, center, half_width_seconds)
    return ToolResult(
        tool_name="get_sensor_history",
        status=ToolStatus.SUCCESS,
        ok=True,
        data={"device_id": device_id, "points": [p.model_dump(mode="json") for p in points]},
    )


@_timed
def summarize_telemetry_window(points: list[TelemetryPoint]) -> ToolResult:
    if not points:
        return ToolResult(
            tool_name="summarize_telemetry_window",
            status=ToolStatus.SUCCESS,
            ok=True,
            data={"count": 0, "has_data": False},
        )
    values = [p.value for p in points]
    stale = any(p.quality_flag.value == "stale" for p in points)
    suspect = any(p.quality_flag.value == "suspect_fault" for p in points)
    return ToolResult(
        tool_name="summarize_telemetry_window",
        status=ToolStatus.SUCCESS,
        ok=True,
        data={
            "count": len(points),
            "has_data": True,
            "min": round(min(values), 1),
            "max": round(max(values), 1),
            "mean": round(sum(values) / len(values), 1),
            "has_stale_reading": stale,
            "has_suspect_fault": suspect,
        },
    )


@_timed
def run_isolation_forest(detector: DeviceAnomalyDetector, device_id: str, value: float) -> ToolResult:
    try:
        result = detector.score(device_id, value)
    except ValueError as exc:
        return ToolResult(tool_name="run_isolation_forest", status=ToolStatus.ERROR, ok=False, error=str(exc))
    return ToolResult(
        tool_name="run_isolation_forest",
        status=ToolStatus.SUCCESS,
        ok=True,
        data={
            "is_anomaly": result.is_anomaly,
            "anomaly_score": round(result.anomaly_score, 4),
            "training_samples": result.training_samples,
        },
    )


@_timed
def retrieve_sop(
    question: str, docs_api_url: str = DEFAULT_DOCS_API_URL, timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS
) -> ToolResult:
    """Calls the FieldForge Docs API's /query endpoint — a real service-to-service
    HTTP call, not an in-process import. See ADR 0002 decision 2 for why, and for the
    degradation behavior when Docs isn't running (status=UNAVAILABLE, not a crash).
    """
    try:
        resp = httpx.post(f"{docs_api_url}/query", json={"question": question, "k": 3}, timeout=timeout)
    except httpx.RequestError as exc:
        return ToolResult(
            tool_name="retrieve_sop",
            status=ToolStatus.UNAVAILABLE,
            ok=False,
            error=f"FieldForge Docs API unreachable at {docs_api_url}: {exc}",
        )
    if resp.status_code != 200:
        return ToolResult(
            tool_name="retrieve_sop",
            status=ToolStatus.ERROR,
            ok=False,
            error=f"Docs API returned {resp.status_code}: {resp.text[:200]}",
        )
    body = resp.json()
    return ToolResult(
        tool_name="retrieve_sop",
        status=ToolStatus.SUCCESS,
        ok=True,
        data={"answer": body["answer"], "refused": body["refused"], "citations": body["citations"]},
    )


@_timed
def draft_maintenance_ticket(
    device_id: str, description: str, risk_level: RiskLevel, estimated_impact: str, alternatives: list[str]
) -> ToolResult:
    """Read-only/preparatory: produces a ProposedAction, persists nothing. The
    corresponding create_maintenance_ticket write only runs after a human approves
    this exact proposal — see apps/copilot_api.
    """
    action = ProposedAction(
        action_type="create_maintenance_ticket",
        tool_name="create_maintenance_ticket",
        arguments={"device_id": device_id, "description": description},
        risk_level=risk_level,
        estimated_impact=estimated_impact,
        alternatives=alternatives,
    )
    return ToolResult(
        tool_name="draft_maintenance_ticket",
        status=ToolStatus.SUCCESS,
        ok=True,
        data={"proposed_action": action.model_dump(mode="json")},
    )
