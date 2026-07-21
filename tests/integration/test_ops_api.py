import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = str(tmp_path / "test_ops.sqlite3")
    monkeypatch.setenv("FIELDFORGE_OPS_DB_PATH", db_path)

    from fieldforge_ops_api import config as config_module

    importlib.reload(config_module)
    from fieldforge_ops_api import main as main_module

    importlib.reload(main_module)

    with TestClient(main_module.app) as c:
        yield c
    main_module.store.close()


DOCS_METRICS_BASELINE = {"recall_at_5": 1.0, "mrr": 0.9, "citation_correctness": 1.0}


def _ingest(client, metrics, is_baseline, source="test"):
    return client.post(
        "/evaluations",
        json={
            "product": "docs",
            "dataset_id": "docs_qa_v1",
            "dataset_version": "v1",
            "case_count": 20,
            "metrics": metrics,
            "is_baseline": is_baseline,
            "source": source,
        },
    )


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["evaluation_runs"] == 0


def test_ingest_evaluation_run(client):
    resp = _ingest(client, DOCS_METRICS_BASELINE, is_baseline=True)
    assert resp.status_code == 201
    run = resp.json()
    assert run["product"] == "docs"
    assert run["is_baseline"] is True


def test_get_unknown_evaluation_run_404(client):
    assert client.get("/evaluations/does-not-exist").status_code == 404


def test_quality_gate_with_no_current_run_404s(client):
    resp = client.post("/quality-gate/run", json={"product": "docs", "dataset_id": "docs_qa_v1"})
    assert resp.status_code == 404


def test_quality_gate_pass(client):
    _ingest(client, DOCS_METRICS_BASELINE, is_baseline=True)
    _ingest(client, DOCS_METRICS_BASELINE, is_baseline=False)
    resp = client.post("/quality-gate/run", json={"product": "docs", "dataset_id": "docs_qa_v1"})
    assert resp.status_code == 201
    assert resp.json()["decision"] == "pass"


def test_quality_gate_fail_on_real_regression(client):
    _ingest(client, DOCS_METRICS_BASELINE, is_baseline=True)
    regressed = dict(DOCS_METRICS_BASELINE, recall_at_5=0.4)
    _ingest(client, regressed, is_baseline=False)
    resp = client.post("/quality-gate/run", json={"product": "docs", "dataset_id": "docs_qa_v1"})
    assert resp.json()["decision"] == "fail"


def test_traces_ingest_and_query(client):
    resp = client.post(
        "/traces",
        json={
            "service": "docs_api",
            "trace_id": "abc",
            "method": "GET",
            "path": "/query",
            "status_code": 200,
        },
    )
    assert resp.status_code == 201
    assert len(client.get("/traces").json()) == 1
    assert len(client.get("/traces?service=docs_api").json()) == 1
    assert len(client.get("/traces?service=nope").json()) == 0


def test_get_trace_by_id(client):
    client.post("/traces", json={"service": "docs_api", "trace_id": "trace-1", "path": "/a"})
    client.post("/traces", json={"service": "docs_api", "trace_id": "trace-1", "path": "/b"})
    spans = client.get("/traces/trace-1").json()
    assert len(spans) == 2


def test_get_unknown_trace_404(client):
    assert client.get("/traces/does-not-exist").status_code == 404


def test_deployment_blocked_without_passing_gate(client):
    ingest_resp = _ingest(client, DOCS_METRICS_BASELINE, is_baseline=False)
    run_id = ingest_resp.json()["id"]
    resp = client.post(
        "/deployments",
        json={
            "product": "docs",
            "environment": "staging",
            "version_label": "v1",
            "evaluation_run_id": run_id,
        },
    )
    assert resp.status_code == 409


def test_deployment_allowed_after_passing_gate(client):
    _ingest(client, DOCS_METRICS_BASELINE, is_baseline=True)
    current = _ingest(client, DOCS_METRICS_BASELINE, is_baseline=False).json()
    client.post("/quality-gate/run", json={"product": "docs", "dataset_id": "docs_qa_v1"})
    resp = client.post(
        "/deployments",
        json={
            "product": "docs",
            "environment": "staging",
            "version_label": "v1",
            "evaluation_run_id": current["id"],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "active"


def test_deployment_blocked_after_failing_gate(client):
    _ingest(client, DOCS_METRICS_BASELINE, is_baseline=True)
    regressed = dict(DOCS_METRICS_BASELINE, recall_at_5=0.1)
    current = _ingest(client, regressed, is_baseline=False).json()
    client.post("/quality-gate/run", json={"product": "docs", "dataset_id": "docs_qa_v1"})
    resp = client.post(
        "/deployments",
        json={
            "product": "docs",
            "environment": "staging",
            "version_label": "v1-bad",
            "evaluation_run_id": current["id"],
        },
    )
    assert resp.status_code == 409


def test_rollback_flow(client):
    _ingest(client, DOCS_METRICS_BASELINE, is_baseline=True)
    current = _ingest(client, DOCS_METRICS_BASELINE, is_baseline=False).json()
    client.post("/quality-gate/run", json={"product": "docs", "dataset_id": "docs_qa_v1"})
    release = client.post(
        "/deployments",
        json={
            "product": "docs",
            "environment": "staging",
            "version_label": "v1",
            "evaluation_run_id": current["id"],
        },
    ).json()

    resp = client.post(
        f"/deployments/{release['id']}/rollback", json={"reason": "bad numbers", "triggered_by": "oncall"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rolled_back"

    events = client.get(f"/deployments/{release['id']}/rollback-events").json()
    assert len(events) == 1
    assert events[0]["reason"] == "bad numbers"


def test_rollback_of_already_rolled_back_release_is_rejected(client):
    _ingest(client, DOCS_METRICS_BASELINE, is_baseline=True)
    current = _ingest(client, DOCS_METRICS_BASELINE, is_baseline=False).json()
    client.post("/quality-gate/run", json={"product": "docs", "dataset_id": "docs_qa_v1"})
    release = client.post(
        "/deployments",
        json={
            "product": "docs",
            "environment": "staging",
            "version_label": "v1",
            "evaluation_run_id": current["id"],
        },
    ).json()
    headers = {"reason": "r", "triggered_by": "t"}
    client.post(f"/deployments/{release['id']}/rollback", json=headers)
    second = client.post(f"/deployments/{release['id']}/rollback", json=headers)
    assert second.status_code == 409


def test_get_unknown_deployment_404(client):
    assert client.get("/deployments/does-not-exist").status_code == 404
