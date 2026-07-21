import pytest
from fastapi.testclient import TestClient
from fieldforge_mesh_telemetry_agent.main import app

VALID_HEADERS = {"X-FieldForge-Agent-Token": "dev-mesh-token"}


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["agent_id"] == "telemetry-analyst"


def test_agent_card_lists_investigate_telemetry_capability(client):
    card = client.get("/.well-known/agent-card").json()
    assert card["id"] == "telemetry-analyst"
    assert "investigate_telemetry" in card["supported_task_types"]
    assert card["auth_required"] is True


def test_create_task_without_token_is_rejected(client):
    resp = client.post("/tasks", json={"task_type": "investigate_telemetry", "input": {}})
    assert resp.status_code == 403


def test_create_task_with_wrong_token_is_rejected(client):
    resp = client.post(
        "/tasks",
        json={"task_type": "investigate_telemetry", "input": {}},
        headers={"X-FieldForge-Agent-Token": "wrong-token"},
    )
    assert resp.status_code == 403


def test_create_task_unsupported_type_is_rejected(client):
    resp = client.post(
        "/tasks", json={"task_type": "not_a_real_task", "input": {}}, headers=VALID_HEADERS
    )
    assert resp.status_code == 400


def test_create_task_missing_fields_is_rejected(client):
    resp = client.post(
        "/tasks",
        json={"task_type": "investigate_telemetry", "input": {"device_id": "FF-R07"}},
        headers=VALID_HEADERS,
    )
    assert resp.status_code == 400


def test_flagship_task_completes_with_sensor_fault_finding(client):
    body = {
        "task_type": "investigate_telemetry",
        "input": {
            "device_id": "FF-R07",
            "value": 1180.0,
            "triggered_at": "2026-06-14T14:32:21+00:00",
            "window_seconds": 42,
            "corroborating_device_id": "FIX-B3-02",
        },
    }
    resp = client.post("/tasks", json=body, headers=VALID_HEADERS)
    assert resp.status_code == 201
    task = resp.json()
    assert task["status"] == "completed"
    finding = task["artifacts"][0]["content"]
    assert finding["rule_based_classification"] == "likely_sensor_fault"
    assert len(task["messages"]) == 2  # requester + agent — real message exchange


def test_task_without_corroborator_is_insufficient_evidence(client):
    body = {
        "task_type": "investigate_telemetry",
        "input": {
            "device_id": "FF-R07",
            "value": 1180.0,
            "triggered_at": "2026-06-14T14:32:21+00:00",
            "window_seconds": 42,
        },
    }
    resp = client.post("/tasks", json=body, headers=VALID_HEADERS)
    finding = resp.json()["artifacts"][0]["content"]
    assert finding["rule_based_classification"] == "insufficient_evidence"


def test_unknown_device_task_fails_gracefully(client):
    body = {
        "task_type": "investigate_telemetry",
        "input": {
            "device_id": "NOT-A-DEVICE",
            "value": 1000.0,
            "triggered_at": "2026-06-14T14:32:21+00:00",
            "window_seconds": 42,
        },
    }
    resp = client.post("/tasks", json=body, headers=VALID_HEADERS)
    assert resp.status_code == 201
    task = resp.json()
    assert task["status"] == "failed"
    assert task["error"] is not None


def test_get_task_by_id(client):
    body = {
        "task_type": "investigate_telemetry",
        "input": {
            "device_id": "FF-R07",
            "value": 1180.0,
            "triggered_at": "2026-06-14T14:32:21+00:00",
            "window_seconds": 42,
            "corroborating_device_id": "FIX-B3-02",
        },
    }
    created = client.post("/tasks", json=body, headers=VALID_HEADERS).json()
    fetched = client.get(f"/tasks/{created['id']}").json()
    assert fetched["id"] == created["id"]


def test_get_unknown_task_404(client):
    assert client.get("/tasks/does-not-exist").status_code == 404


def test_cancel_completed_task_returns_real_terminal_status(client):
    body = {
        "task_type": "investigate_telemetry",
        "input": {
            "device_id": "FF-R07",
            "value": 1180.0,
            "triggered_at": "2026-06-14T14:32:21+00:00",
            "window_seconds": 42,
            "corroborating_device_id": "FIX-B3-02",
        },
    }
    created = client.post("/tasks", json=body, headers=VALID_HEADERS).json()
    cancelled = client.post(f"/tasks/{created['id']}/cancel").json()
    assert cancelled["status"] == "completed"  # already terminal — see ADR 0003 decision 6
