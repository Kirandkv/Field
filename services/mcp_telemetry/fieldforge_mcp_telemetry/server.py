"""telemetry-mcp — a real MCP server (official `mcp` SDK) exposing FieldForge's
telemetry tools: query_telemetry, compare_devices, run_anomaly_detection,
get_sensor_metadata. Any MCP client (Claude Desktop, an MCP inspector, another
agent) can connect to this over streamable HTTP — it is not a FieldForge-only
protocol. See docs/adr/0003-mesh-agent-protocol.md decision 3.

Run: python -m fieldforge_mcp_telemetry.server
"""

from __future__ import annotations

import os
from datetime import datetime

from fieldforge_anomaly import DeviceAnomalyDetector
from fieldforge_telemetry import TelemetryStore
from mcp.server.fastmcp import FastMCP

from fieldforge_mcp_telemetry import core

_HOST = os.getenv("FIELDFORGE_MCP_TELEMETRY_HOST", "127.0.0.1")
_PORT = int(os.getenv("FIELDFORGE_MCP_TELEMETRY_PORT", "8020"))

mcp = FastMCP("fieldforge-telemetry-mcp", host=_HOST, port=_PORT, stateless_http=True)

_store = TelemetryStore()
_detector = DeviceAnomalyDetector()
for _device in _store.list_devices():
    _values = [p.value for p in _store.get_history(_device.id)]
    if len(_values) >= 10:
        _detector.fit(_device.id, _values)


@mcp.tool()
def query_telemetry(device_id: str, center_iso: str, half_width_seconds: float) -> dict:
    """Return the telemetry summary (count/min/max/mean/quality flags) for a device
    within half_width_seconds of the given center timestamp (ISO 8601).
    """
    return core.query_telemetry(_store, device_id, datetime.fromisoformat(center_iso), half_width_seconds)


@mcp.tool()
def compare_devices(
    device_id: str, corroborating_device_id: str, center_iso: str, half_width_seconds: float
) -> dict:
    """Compare a device's reading against a corroborating device for the same
    window and return SOP-014's rule-based classification
    (likely_real_event / likely_sensor_fault / insufficient_evidence).
    """
    return core.compare_devices(
        _store, device_id, corroborating_device_id, datetime.fromisoformat(center_iso), half_width_seconds
    )


@mcp.tool()
def run_anomaly_detection(device_id: str, value: float) -> dict:
    """Score a reading against the device's own Isolation Forest model, fit on its
    historical telemetry at server startup.
    """
    return core.run_anomaly_detection(_detector, device_id, value)


@mcp.tool()
def get_sensor_metadata(device_id: str) -> dict:
    """Return device registry metadata (name, type, site, status)."""
    return core.get_sensor_metadata(_store, device_id)


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
