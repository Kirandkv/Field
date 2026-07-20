import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = str(tmp_path / "test_copilot.sqlite3")
    monkeypatch.setenv("FIELDFORGE_COPILOT_DB_PATH", db_path)
    # Unreachable on purpose: the API test suite must be deterministic and offline —
    # see tests/unit/test_orchestrator.py for the graceful-degradation coverage this
    # relies on (retrieve_sop returning UNAVAILABLE rather than crashing).
    monkeypatch.setenv("FIELDFORGE_DOCS_API_URL", "http://127.0.0.1:1")

    from fieldforge_copilot_api import config as config_module

    importlib.reload(config_module)
    from fieldforge_copilot_api import main as main_module

    importlib.reload(main_module)

    with TestClient(main_module.app) as c:
        yield c
    main_module.store.close()


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_trigger_unknown_demo_scenario_404(client):
    resp = client.post("/demo/scenarios/does-not-exist/trigger")
    assert resp.status_code == 404


def test_sensor_fault_scenario_reaches_awaiting_approval(client):
    resp = client.post("/demo/scenarios/alert-2026-06-14/trigger")
    assert resp.status_code == 201
    incident = resp.json()
    assert incident["state"] == "awaiting_approval"
    assert incident["classification"] == "likely_sensor_fault"

    approvals = client.get("/approvals").json()
    assert len(approvals) == 1
    assert approvals[0]["incident_id"] == incident["id"]


def test_insufficient_evidence_scenario_has_no_approval(client):
    resp = client.post("/demo/scenarios/alert-2026-07-10/trigger")
    incident = resp.json()
    assert incident["state"] == "requesting_more_evidence"
    assert client.get("/approvals").json() == []


def test_decision_without_role_header_is_rejected(client):
    trigger = client.post("/demo/scenarios/alert-2026-06-14/trigger").json()
    approval_id = client.get("/approvals").json()[0]["id"]
    resp = client.post(f"/approvals/{approval_id}/decision", json={"decision": "approve"})
    assert resp.status_code == 403
    # Unauthorized attempt must not move the incident forward.
    incident = client.get(f"/incidents/{trigger['id']}").json()
    assert incident["state"] == "awaiting_approval"


def test_decision_with_wrong_role_is_rejected(client):
    client.post("/demo/scenarios/alert-2026-06-14/trigger")
    approval_id = client.get("/approvals").json()[0]["id"]
    resp = client.post(
        f"/approvals/{approval_id}/decision",
        json={"decision": "approve"},
        headers={"X-FieldForge-Role": "engineer"},
    )
    assert resp.status_code == 403


def test_approve_with_safety_manager_role_creates_ticket(client):
    trigger = client.post("/demo/scenarios/alert-2026-06-14/trigger").json()
    approval_id = client.get("/approvals").json()[0]["id"]
    resp = client.post(
        f"/approvals/{approval_id}/decision",
        json={"decision": "approve"},
        headers={"X-FieldForge-Role": "safety_manager"},
    )
    assert resp.status_code == 200
    incident = resp.json()
    assert incident["state"] == "completed"

    tickets = client.get("/tickets").json()
    assert len(tickets) == 1
    assert tickets[0]["incident_id"] == trigger["id"]
    assert tickets[0]["approved_by"] == "role:safety_manager"


def test_modify_and_approve_uses_modified_arguments(client):
    client.post("/demo/scenarios/alert-2026-06-14/trigger")
    approval_id = client.get("/approvals").json()[0]["id"]
    resp = client.post(
        f"/approvals/{approval_id}/decision",
        json={
            "decision": "modify_and_approve",
            "modified_arguments": {"device_id": "FF-R07", "description": "Modified by safety manager"},
        },
        headers={"X-FieldForge-Role": "safety_manager"},
    )
    assert resp.status_code == 200
    tickets = client.get("/tickets").json()
    assert tickets[0]["description"] == "Modified by safety manager"


def test_reject_does_not_create_a_ticket(client):
    client.post("/demo/scenarios/alert-2026-06-14/trigger")
    approval_id = client.get("/approvals").json()[0]["id"]
    resp = client.post(
        f"/approvals/{approval_id}/decision",
        json={"decision": "reject", "reason": "not convinced"},
        headers={"X-FieldForge-Role": "safety_manager"},
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "rejected"
    assert client.get("/tickets").json() == []


def test_deciding_an_already_decided_approval_is_rejected(client):
    client.post("/demo/scenarios/alert-2026-06-14/trigger")
    approval_id = client.get("/approvals").json()[0]["id"]
    headers = {"X-FieldForge-Role": "safety_manager"}
    first = client.post(f"/approvals/{approval_id}/decision", json={"decision": "approve"}, headers=headers)
    assert first.status_code == 200
    second = client.post(f"/approvals/{approval_id}/decision", json={"decision": "approve"}, headers=headers)
    assert second.status_code == 409


def test_unknown_device_alert_reaches_failed_state(client):
    resp = client.post(
        "/alerts",
        json={
            "device_id": "NOT-A-REAL-DEVICE",
            "metric": "methane_ppm",
            "value": 1200,
            "window_seconds": 40,
            "triggered_at": "2026-07-15T10:00:00Z",
            "corroborating_device_id": "FIX-B3-02",
        },
    )
    assert resp.status_code == 201
    incident = resp.json()
    assert incident["state"] == "failed"
    assert incident["error"] is not None


def test_get_unknown_incident_404(client):
    assert client.get("/incidents/does-not-exist").status_code == 404


def test_get_unknown_approval_404(client):
    assert client.get("/approvals/does-not-exist").status_code == 404
