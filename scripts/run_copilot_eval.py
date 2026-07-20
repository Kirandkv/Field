"""Runs the FieldForge Copilot slice-1 scenario suite and writes a real, measured
report. Uses FastAPI's TestClient in-process, with the Docs API URL deliberately
unreachable — deterministic and offline, same posture as tests/integration/test_copilot_api.py.
See docs/EVALUATION_METHODOLOGY.md.

Usage: python scripts/run_copilot_eval.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DATASET = REPO_ROOT / "evals" / "datasets" / "copilot_scenarios_v1.jsonl"
REPORTS_DIR = REPO_ROOT / "evals" / "reports"
DATASET_VERSION = "v1"


def load_jsonl(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _decide(
    client,
    approval_id: str,
    decision: str,
    headers: dict | None = None,
    modified_arguments: dict | None = None,
):
    body: dict = {"decision": decision}
    if modified_arguments is not None:
        body["modified_arguments"] = modified_arguments
    return client.post(f"/approvals/{approval_id}/decision", json=body, headers=headers or {})


def _fresh_client(tmp_db_path: str):
    import os

    os.environ["FIELDFORGE_COPILOT_DB_PATH"] = tmp_db_path
    os.environ["FIELDFORGE_DOCS_API_URL"] = "http://127.0.0.1:1"  # deliberately unreachable

    import importlib

    from fieldforge_copilot_api import config as config_module

    importlib.reload(config_module)
    from fieldforge_copilot_api import main as main_module

    importlib.reload(main_module)

    from fastapi.testclient import TestClient

    return TestClient(main_module.app), main_module


def run_case(case: dict, tmp_dir: Path) -> dict:
    client, main_module = _fresh_client(str(tmp_dir / f"{case['id']}.sqlite3"))
    start = time.perf_counter()
    result = {"id": case["id"], "type": case["type"], "pass": False, "detail": {}}

    try:
        if case["type"] == "classification":
            resp = client.post(f"/demo/scenarios/{case['scenario_id']}/trigger")
            incident = resp.json()
            ok = (
                resp.status_code == 201
                and incident["classification"] == case["expected_classification"]
                and incident["state"] == case["expected_state"]
            )
            if "expected_risk" in case and ok:
                approvals = client.get("/approvals").json()
                ok = bool(approvals) and approvals[0]["risk_level"] == case["expected_risk"]
            result["pass"] = ok
            result["detail"] = {
                "classification": incident.get("classification"),
                "state": incident.get("state"),
            }

        elif case["type"] == "tool_failure":
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
            incident = resp.json()
            ok = resp.status_code == 201 and incident["state"] == case["expected_state"] and incident["error"]
            result["pass"] = bool(ok)
            result["detail"] = {"state": incident.get("state"), "http_status": resp.status_code}

        elif case["type"] in ("approve_flow", "reject_flow", "modify_and_approve_flow"):
            client.post(f"/demo/scenarios/{case['scenario_id']}/trigger")
            approval_id = client.get("/approvals").json()[0]["id"]
            headers = {"X-FieldForge-Role": "safety_manager"}
            if case["type"] == "reject_flow":
                resp = _decide(client, approval_id, "reject", headers)
            elif case["type"] == "modify_and_approve_flow":
                modified = {"device_id": "FF-R07", "description": "Modified description"}
                resp = _decide(client, approval_id, "modify_and_approve", headers, modified)
            else:
                resp = _decide(client, approval_id, "approve", headers)
            incident = resp.json()
            tickets = client.get("/tickets").json()
            ok = resp.status_code == 200 and incident["state"] == case["expected_final_state"]
            ok = ok and (bool(tickets) == case["expect_ticket"])
            if case.get("expect_modified_description") and ok:
                ok = tickets[0]["description"] == "Modified description"
            result["pass"] = ok
            result["detail"] = {"state": incident.get("state"), "ticket_count": len(tickets)}

        elif case["type"] == "unauthorized_action":
            client.post(f"/demo/scenarios/{case['scenario_id']}/trigger")
            incident_before = client.get("/incidents").json()[0]
            approval_id = client.get("/approvals").json()[0]["id"]
            role_headers = {"X-FieldForge-Role": case["role_header"]} if case["role_header"] else None
            resp = _decide(client, approval_id, "approve", role_headers)
            incident_after = client.get(f"/incidents/{incident_before['id']}").json()
            ok = (
                resp.status_code == case["expected_http_status"]
                and incident_after["state"] == "awaiting_approval"
            )
            result["pass"] = ok
            result["detail"] = {"http_status": resp.status_code, "state_after": incident_after["state"]}

        elif case["type"] == "idempotency":
            client.post(f"/demo/scenarios/{case['scenario_id']}/trigger")
            approval_id = client.get("/approvals").json()[0]["id"]
            headers = {"X-FieldForge-Role": "safety_manager"}
            first = _decide(client, approval_id, "approve", headers)
            second = _decide(client, approval_id, "approve", headers)
            ok = first.status_code == 200 and second.status_code == case["expected_second_decision_status"]
            result["pass"] = ok
            result["detail"] = {"first_status": first.status_code, "second_status": second.status_code}

        elif case["type"] == "degraded_evidence":
            resp = client.post(f"/demo/scenarios/{case['scenario_id']}/trigger")
            incident = resp.json()
            has_sop = any(e["kind"] == "sop_citation" for e in incident["evidence"])
            ok = incident["state"] == case["expected_state"] and has_sop == case["expect_sop_evidence"]
            result["pass"] = ok
            result["detail"] = {"state": incident.get("state"), "has_sop_evidence": has_sop}

        else:
            raise ValueError(f"unknown scenario type: {case['type']}")
    finally:
        main_module.store.close()

    result["latency_ms"] = round((time.perf_counter() - start) * 1000, 3)
    return result


def main() -> None:
    import tempfile

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    cases = load_jsonl(DATASET)

    with tempfile.TemporaryDirectory() as tmp:
        results = [run_case(case, Path(tmp)) for case in cases]

    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    unauthorized = [r for r in results if r["type"] == "unauthorized_action"]
    recovery = [r for r in results if r["type"] in ("tool_failure", "degraded_evidence")]
    human_decision_types = ("approve_flow", "reject_flow", "modify_and_approve_flow", "idempotency")
    human_decision = [r for r in results if r["type"] in human_decision_types]
    latencies = sorted(r["latency_ms"] for r in results)

    def _rate(subset: list[dict]) -> float:
        return round(sum(1 for r in subset if r["pass"]) / len(subset), 3) if subset else 0.0

    def _pct(values: list[float], pct: float) -> float:
        if not values:
            return 0.0
        idx = min(len(values) - 1, int(round(pct / 100 * (len(values) - 1))))
        return round(values[idx], 3)

    report = {
        "dataset_id": "copilot_scenarios_v1",
        "dataset_version": DATASET_VERSION,
        "case_count": total,
        "goal_completion_rate": round(passed / total, 3) if total else 0.0,
        "unauthorized_action_prevention_rate": _rate(unauthorized),
        "recovery_after_failure_rate": _rate(recovery),
        "human_decision_handling_rate": _rate(human_decision),
        "latency_ms_p50": _pct(latencies, 50),
        "latency_ms_p95": _pct(latencies, 95),
        "detail": results,
        "limitations": (
            "12 hand-authored scenarios over a 3-device synthetic fleet; not the "
            "50-scenario suite the program brief specifies for a full Copilot "
            "evaluation — see docs/ROADMAP.md. Every scenario here is a real "
            "assertion against real code, not a placeholder."
        ),
    }

    (REPORTS_DIR / "copilot_scenarios_v1_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    print("=== FieldForge Copilot — Slice 1 Evaluation ===")
    for key in (
        "case_count",
        "goal_completion_rate",
        "unauthorized_action_prevention_rate",
        "recovery_after_failure_rate",
        "human_decision_handling_rate",
        "latency_ms_p50",
        "latency_ms_p95",
    ):
        print(f"{key}: {report[key]}")
    for r in results:
        print(f"  [{'PASS' if r['pass'] else 'FAIL'}] {r['id']} ({r['type']}) {r['detail']}")

    if any(not r["pass"] for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
