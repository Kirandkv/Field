from datetime import UTC, datetime

from fieldforge_agent_copilot import tools
from fieldforge_anomaly import DeviceAnomalyDetector
from fieldforge_contracts import (
    DataQualityFlag,
    RiskLevel,
    SensorMetric,
    TelemetryPoint,
    ToolStatus,
)
from fieldforge_telemetry import TelemetryStore


def _point(value, quality=DataQualityFlag.OK):
    return TelemetryPoint(
        device_id="FF-R07",
        metric=SensorMetric.METHANE_PPM,
        value=value,
        timestamp=datetime(2026, 6, 14, 14, 32, tzinfo=UTC),
        quality_flag=quality,
    )


def test_get_device_unknown_returns_error_status():
    store = TelemetryStore()
    result = tools.get_device(store, "NOT-A-DEVICE")
    assert result.status == ToolStatus.ERROR
    assert result.ok is False


def test_get_device_known_returns_success():
    store = TelemetryStore()
    result = tools.get_device(store, "FF-R07")
    assert result.ok is True
    assert result.data["id"] == "FF-R07"


def test_summarize_telemetry_window_empty():
    result = tools.summarize_telemetry_window([])
    assert result.ok is True
    assert result.data == {"count": 0, "has_data": False}


def test_summarize_telemetry_window_computes_stats():
    points = [_point(10.0), _point(20.0), _point(30.0)]
    result = tools.summarize_telemetry_window(points)
    assert result.data["count"] == 3
    assert result.data["min"] == 10.0
    assert result.data["max"] == 30.0
    assert result.data["mean"] == 20.0
    assert result.data["has_stale_reading"] is False


def test_summarize_telemetry_window_flags_stale():
    points = [_point(10.0), _point(10.0, quality=DataQualityFlag.STALE)]
    result = tools.summarize_telemetry_window(points)
    assert result.data["has_stale_reading"] is True


def test_run_isolation_forest_error_on_unfitted_device():
    detector = DeviceAnomalyDetector()
    result = tools.run_isolation_forest(detector, "FF-R07", 1000.0)
    assert result.status == ToolStatus.ERROR
    assert result.ok is False


def test_run_isolation_forest_success():
    detector = DeviceAnomalyDetector()
    detector.fit("FF-R07", [10.0, 9.5, 10.2, 9.8, 10.1, 9.9, 10.3, 9.7, 10.0, 9.6])
    result = tools.run_isolation_forest(detector, "FF-R07", 5000.0)
    assert result.ok is True
    assert result.data["is_anomaly"] is True


def test_retrieve_sop_returns_unavailable_when_docs_api_unreachable():
    result = tools.retrieve_sop("methane response procedure", docs_api_url="http://127.0.0.1:1", timeout=1.0)
    assert result.status == ToolStatus.UNAVAILABLE
    assert result.ok is False
    assert "unreachable" in result.error


def test_draft_maintenance_ticket_produces_proposed_action():
    result = tools.draft_maintenance_ticket(
        device_id="FF-R07",
        description="recalibrate sensor",
        risk_level=RiskLevel.MEDIUM,
        estimated_impact="scheduling record only",
        alternatives=["escalate instead"],
    )
    assert result.ok is True
    action = result.data["proposed_action"]
    assert action["tool_name"] == "create_maintenance_ticket"
    assert action["arguments"]["device_id"] == "FF-R07"
    assert action["risk_level"] == "medium"
