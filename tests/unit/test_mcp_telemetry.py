import asyncio
from datetime import UTC, datetime

from fieldforge_anomaly import DeviceAnomalyDetector
from fieldforge_mcp_telemetry import core
from fieldforge_telemetry import TelemetryStore


def _store() -> TelemetryStore:
    return TelemetryStore()


def test_query_telemetry_unknown_device_returns_error():
    result = core.query_telemetry(_store(), "NOT-A-DEVICE", datetime.now(UTC), 60)
    assert result["ok"] is False


def test_query_telemetry_known_device_returns_summary():
    store = _store()
    center = datetime(2026, 6, 14, 14, 32, 21, tzinfo=UTC)
    result = core.query_telemetry(store, "FF-R07", center, 42)
    assert result["ok"] is True
    assert result["summary"]["has_data"] is True
    assert result["summary"]["max"] > 1000


def test_compare_devices_flagship_scenario_classifies_sensor_fault():
    store = _store()
    center = datetime(2026, 6, 14, 14, 32, 21, tzinfo=UTC)
    result = core.compare_devices(store, "FF-R07", "FIX-B3-02", center, 42)
    assert result["rule_based_classification"] == "likely_sensor_fault"
    assert result["corroborating_summary"]["max"] < 100


def test_compare_devices_real_event_scenario_classifies_real_event():
    store = _store()
    center = datetime(2026, 7, 8, 11, 5, 25, tzinfo=UTC)
    result = core.compare_devices(store, "FF-R07", "FIX-B3-02", center, 50)
    assert result["rule_based_classification"] == "likely_real_event"


def test_compare_devices_stale_corroborator_is_insufficient_evidence():
    store = _store()
    center = datetime(2026, 7, 10, 16, 40, 19, tzinfo=UTC)
    result = core.compare_devices(store, "FF-R07", "FIX-B3-02", center, 38)
    assert result["rule_based_classification"] == "insufficient_evidence"


def test_run_anomaly_detection_without_fit_returns_error():
    detector = DeviceAnomalyDetector()
    result = core.run_anomaly_detection(detector, "FF-R07", 1000.0)
    assert result["ok"] is False


def test_run_anomaly_detection_flags_extreme_reading():
    detector = DeviceAnomalyDetector()
    detector.fit("FF-R07", [10.0, 9.5, 10.2, 9.8, 10.1, 9.9, 10.3, 9.7, 10.0, 9.6])
    result = core.run_anomaly_detection(detector, "FF-R07", 5000.0)
    assert result["ok"] is True
    assert result["is_anomaly"] is True


def test_get_sensor_metadata_known_device():
    result = core.get_sensor_metadata(_store(), "FF-R07")
    assert result["ok"] is True
    assert result["device"]["id"] == "FF-R07"


def test_get_sensor_metadata_unknown_device():
    result = core.get_sensor_metadata(_store(), "NOT-A-DEVICE")
    assert result["ok"] is False


def test_mcp_server_registers_the_four_required_tools():
    from fieldforge_mcp_telemetry.server import mcp

    async def _list():
        return await mcp.list_tools()

    tools = asyncio.run(_list())
    names = {t.name for t in tools}
    assert names == {
        "query_telemetry",
        "compare_devices",
        "run_anomaly_detection",
        "get_sensor_metadata",
    }


def test_mcp_server_tool_call_returns_real_classification():
    from fieldforge_mcp_telemetry.server import mcp

    async def _call():
        return await mcp.call_tool(
            "compare_devices",
            {
                "device_id": "FF-R07",
                "corroborating_device_id": "FIX-B3-02",
                "center_iso": "2026-06-14T14:32:21+00:00",
                "half_width_seconds": 42,
            },
        )

    result = asyncio.run(_call())
    assert "likely_sensor_fault" in result[0].text
