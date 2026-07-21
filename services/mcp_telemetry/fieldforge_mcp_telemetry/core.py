"""Pure tool implementations shared by telemetry-mcp's MCP transport
(server.py) and the Telemetry Analyst A2A agent (apps/mesh_telemetry_agent) —
one implementation, two transports, per docs/adr/0003-mesh-agent-protocol.md.

The corroboration classification policy here mirrors FieldForge Copilot's
(services/agent_copilot/orchestrator.py) implementation of SOP-014. This is a
deliberate, disclosed duplication across product boundaries — Telemetry Analyst and
Copilot are different agents in different products, each independently implementing
the same written procedure, the way two real services calling the same SOP would.
"""

from __future__ import annotations

from datetime import datetime

from fieldforge_anomaly import DeviceAnomalyDetector
from fieldforge_contracts import TelemetryPoint
from fieldforge_telemetry import TelemetryStore

CORROBORATION_ELEVATED_PPM = 100
MIN_CORROBORATION_HALF_WIDTH_S = 700


def summarize_points(points: list[TelemetryPoint]) -> dict:
    if not points:
        return {"count": 0, "has_data": False}
    values = [p.value for p in points]
    return {
        "count": len(points),
        "has_data": True,
        "min": round(min(values), 1),
        "max": round(max(values), 1),
        "mean": round(sum(values) / len(values), 1),
        "has_stale_reading": any(p.quality_flag.value == "stale" for p in points),
        "has_suspect_fault": any(p.quality_flag.value == "suspect_fault" for p in points),
    }


def query_telemetry(
    store: TelemetryStore, device_id: str, center: datetime, half_width_seconds: float
) -> dict:
    device = store.get_device(device_id)
    if device is None:
        return {"ok": False, "error": f"unknown device {device_id!r}"}
    points = store.get_window(device_id, center, half_width_seconds)
    return {"ok": True, "device_id": device_id, "summary": summarize_points(points)}


def compare_devices(
    store: TelemetryStore,
    device_id: str,
    corroborating_device_id: str,
    center: datetime,
    half_width_seconds: float,
) -> dict:
    primary_points = store.get_window(device_id, center, half_width_seconds)
    primary_summary = summarize_points(primary_points)

    corr_half_width = max(half_width_seconds, MIN_CORROBORATION_HALF_WIDTH_S)
    corr_points = store.get_window(corroborating_device_id, center, corr_half_width)
    corr_summary = summarize_points(corr_points)

    if not corr_summary.get("has_data") or corr_summary.get("has_stale_reading"):
        classification = "insufficient_evidence"
    elif corr_summary.get("max", 0) > CORROBORATION_ELEVATED_PPM:
        classification = "likely_real_event"
    else:
        classification = "likely_sensor_fault"

    return {
        "ok": True,
        "device_id": device_id,
        "corroborating_device_id": corroborating_device_id,
        "primary_summary": primary_summary,
        "corroborating_summary": corr_summary,
        "rule_based_classification": classification,
    }


def run_anomaly_detection(detector: DeviceAnomalyDetector, device_id: str, value: float) -> dict:
    try:
        result = detector.score(device_id, value)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "is_anomaly": result.is_anomaly,
        "anomaly_score": round(result.anomaly_score, 4),
        "training_samples": result.training_samples,
    }


def get_sensor_metadata(store: TelemetryStore, device_id: str) -> dict:
    device = store.get_device(device_id)
    if device is None:
        return {"ok": False, "error": f"unknown device {device_id!r}"}
    return {"ok": True, "device": device.model_dump(mode="json")}
