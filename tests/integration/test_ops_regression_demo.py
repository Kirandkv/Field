"""The CI/CD regression demonstration the program brief calls a primary portfolio
feature: baseline passes -> a real regression is introduced -> the gate fails ->
the regression is fixed -> the gate passes -> deploy to staging -> canary ->
simulate an online regression -> rollback. See ADR 0004 decision 4 for why this is
a test against real Ops API code rather than a scheduled CI job that deliberately
breaks a product.

The "regression" here is a copy of the real, committed Docs baseline
(evals/baselines/docs_v1_baseline.json) with citation_correctness lowered — a
believable prompt/retrieval regression, not an arbitrary number.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / "evals" / "baselines" / "docs_v1_baseline.json"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("FIELDFORGE_OPS_DB_PATH", str(tmp_path / "test_ops_regression.sqlite3"))

    from fieldforge_ops_api import config as config_module

    importlib.reload(config_module)
    from fieldforge_ops_api import main as main_module

    importlib.reload(main_module)

    with TestClient(main_module.app) as c:
        yield c
    main_module.store.close()


def _load_real_baseline_metrics() -> dict:
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return {
        k: v
        for k, v in data.items()
        if k not in ("dataset_id", "dataset_version", "case_count", "detail", "limitations")
    }


def _ingest(client, metrics, is_baseline, source):
    resp = client.post(
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
    resp.raise_for_status()
    return resp.json()


def test_full_regression_to_rollback_sequence(client):
    real_baseline_metrics = _load_real_baseline_metrics()
    assert real_baseline_metrics, "expected a non-empty baseline in evals/baselines/docs_v1_baseline.json"

    # Step 1: ingest the real committed baseline.
    _ingest(client, real_baseline_metrics, is_baseline=True, source="evals/baselines/docs_v1_baseline.json")

    # Step 2: a PR run with identical numbers passes the gate (sanity check).
    _ingest(client, real_baseline_metrics, is_baseline=False, source="pr-run-1")
    gate1 = client.post("/quality-gate/run", json={"product": "docs", "dataset_id": "docs_qa_v1"}).json()
    assert gate1["decision"] == "pass"

    # Step 3: a real regression — a prompt/retrieval change drops citation
    # correctness well below the baseline (believable failure mode: the model
    # starts citing chunks that don't actually support the claim).
    regressed_metrics = dict(real_baseline_metrics, citation_correctness=0.4)
    regressed_run = _ingest(client, regressed_metrics, is_baseline=False, source="pr-run-2-regressed")
    gate2 = client.post("/quality-gate/run", json={"product": "docs", "dataset_id": "docs_qa_v1"}).json()
    assert gate2["decision"] == "fail"
    citation_comparison = next(c for c in gate2["comparisons"] if c["metric_name"] == "citation_correctness")
    assert citation_comparison["status"] == "fail"

    # Step 4: the regression blocks deployment — this is the gate actually doing
    # something, not just reporting a number.
    blocked = client.post(
        "/deployments",
        json={
            "product": "docs",
            "environment": "staging",
            "version_label": "v1.1.0-regressed",
            "evaluation_run_id": regressed_run["id"],
        },
    )
    assert blocked.status_code == 409

    # Step 5: the regression is fixed — a new run with the original numbers.
    fixed_run = _ingest(client, real_baseline_metrics, is_baseline=False, source="pr-run-3-fixed")
    gate3 = client.post("/quality-gate/run", json={"product": "docs", "dataset_id": "docs_qa_v1"}).json()
    assert gate3["decision"] == "pass"

    # Step 6: deploy to staging (canary_percent default 100 — full traffic for this
    # slice; partial canary rollout is a planned M2 item, see ADR 0004).
    release = client.post(
        "/deployments",
        json={
            "product": "docs",
            "environment": "staging",
            "version_label": "v1.1.0-fixed",
            "evaluation_run_id": fixed_run["id"],
        },
    ).json()
    assert release["status"] == "active"

    # Step 7: simulate an online regression discovered after deploy — an operator
    # rolls back the release.
    rollback = client.post(
        f"/deployments/{release['id']}/rollback",
        json={"reason": "elevated error rate observed post-deploy", "triggered_by": "oncall-engineer"},
    ).json()
    assert rollback["status"] == "rolled_back"

    events = client.get(f"/deployments/{release['id']}/rollback-events").json()
    assert len(events) == 1
    assert events[0]["reason"] == "elevated error rate observed post-deploy"

    # Sanity: the full history is queryable end to end.
    all_runs = client.get("/evaluations?product=docs").json()
    assert len(all_runs) == 4  # baseline + good + regressed + fixed
    all_gates = client.get("/quality-gate?product=docs").json()
    assert len(all_gates) == 3
    assert {g["decision"] for g in all_gates} == {"pass", "fail"}
