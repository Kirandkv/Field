"""Incident Commander integration tests.

Runs a real Telemetry Analyst server in a background thread rather than mocking
HTTP — Commander's whole point is real cross-process A2A delegation, so a mock would
test nothing meaningful about that. Following the suite's "don't mock everything"
testing standard.
"""

from __future__ import annotations

import importlib
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from fieldforge_mesh_telemetry_agent.main import app as telemetry_app

TELEMETRY_TEST_PORT = 8931
TELEMETRY_TEST_URL = f"http://127.0.0.1:{TELEMETRY_TEST_PORT}"

FLAGSHIP_INPUT = {
    "device_id": "FF-R07",
    "value": 1180.0,
    "triggered_at": "2026-06-14T14:32:21+00:00",
    "window_seconds": 42,
    "corroborating_device_id": "FIX-B3-02",
}


@pytest.fixture(scope="module")
def telemetry_server():
    config = uvicorn.Config(telemetry_app, host="127.0.0.1", port=TELEMETRY_TEST_PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 15
    up = False
    while time.time() < deadline:
        try:
            if httpx.get(f"{TELEMETRY_TEST_URL}/health", timeout=0.5).status_code == 200:
                up = True
                break
        except httpx.RequestError:
            time.sleep(0.2)
    if not up:
        raise RuntimeError("telemetry agent test server did not start in time")

    yield TELEMETRY_TEST_URL

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture()
def commander_client(monkeypatch, tmp_path):
    db_path = str(tmp_path / "test_commander.sqlite3")
    monkeypatch.setenv("FIELDFORGE_MESH_COMMANDER_DB_PATH", db_path)

    from fieldforge_mesh_commander import config as config_module

    importlib.reload(config_module)
    from fieldforge_mesh_commander import main as main_module

    importlib.reload(main_module)

    with TestClient(main_module.app) as c:
        yield c
    main_module.store.close()


def test_health_ok(commander_client):
    resp = commander_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["registered_agents"] == 0


def test_investigate_without_registered_analyst_degrades(commander_client):
    resp = commander_client.post("/incidents", json=FLAGSHIP_INPUT)
    assert resp.status_code == 201
    report = resp.json()
    assert "degraded_no_analyst_evidence" in report["safety_decision"]
    assert report["requires_human_approval"] is True
    assert report["analyst_finding"] is None


def test_discover_unreachable_endpoint_returns_502(commander_client):
    resp = commander_client.post("/agents/discover", json={"endpoint": "http://127.0.0.1:1"})
    assert resp.status_code == 502


def test_discover_and_investigate_real_telemetry_analyst(commander_client, telemetry_server):
    discover = commander_client.post("/agents/discover", json={"endpoint": telemetry_server})
    assert discover.status_code == 201
    card = discover.json()
    assert card["id"] == "telemetry-analyst"

    agents = commander_client.get("/agents").json()
    assert len(agents) == 1

    resp = commander_client.post("/incidents", json=FLAGSHIP_INPUT)
    assert resp.status_code == 201
    report = resp.json()
    assert report["safety_decision"] == "recommend_recalibration_pending_safety_review"
    assert report["requires_human_approval"] is True
    assert report["analyst_finding"]["rule_based_classification"] == "likely_sensor_fault"
    assert len(report["delegation_log"]) == 1
    assert report["delegation_log"][0]["status"] == "completed"


def test_real_event_scenario_escalates(commander_client, telemetry_server):
    commander_client.post("/agents/discover", json={"endpoint": telemetry_server})
    body = {
        "device_id": "FF-R07",
        "value": 1400.0,
        "triggered_at": "2026-07-08T11:05:25+00:00",
        "window_seconds": 50,
        "corroborating_device_id": "FIX-B3-02",
    }
    resp = commander_client.post("/incidents", json=body)
    report = resp.json()
    assert report["safety_decision"] == "escalate_immediately_to_safety_manager"
    assert report["analyst_finding"]["rule_based_classification"] == "likely_real_event"


def test_unknown_device_produces_degraded_report(commander_client, telemetry_server):
    commander_client.post("/agents/discover", json={"endpoint": telemetry_server})
    body = {
        "device_id": "NOT-A-DEVICE",
        "value": 1000.0,
        "triggered_at": "2026-06-14T14:32:21+00:00",
        "window_seconds": 42,
        "corroborating_device_id": "FIX-B3-02",
    }
    resp = commander_client.post("/incidents", json=body)
    report = resp.json()
    assert "degraded_no_analyst_evidence" in report["safety_decision"]
    assert report["error"] is not None


def test_get_incident_by_id(commander_client, telemetry_server):
    commander_client.post("/agents/discover", json={"endpoint": telemetry_server})
    created = commander_client.post("/incidents", json=FLAGSHIP_INPUT).json()
    fetched = commander_client.get(f"/incidents/{created['id']}").json()
    assert fetched["id"] == created["id"]


def test_get_unknown_incident_404(commander_client):
    assert commander_client.get("/incidents/does-not-exist").status_code == 404


def test_register_agent_directly(commander_client):
    card = {
        "id": "manual-agent",
        "name": "Manually Registered",
        "role": "test-role",
        "capabilities": [],
        "supported_task_types": [],
        "auth_required": False,
        "endpoint": "http://example.invalid",
    }
    resp = commander_client.post("/agents/register", json=card)
    assert resp.status_code == 201
    assert any(a["id"] == "manual-agent" for a in commander_client.get("/agents").json())
