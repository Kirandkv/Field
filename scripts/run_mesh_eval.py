"""Runs the FieldForge Mesh slice-1 scenario suite against two real services: a
Telemetry Analyst started in a background thread (real HTTP, real port) and a fresh
Incident Commander per scenario. No mocked HTTP — Mesh's whole point is real
cross-process A2A delegation. See docs/EVALUATION_METHODOLOGY.md.

Usage: python scripts/run_mesh_eval.py
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from fieldforge_mesh_telemetry_agent.main import app as telemetry_app  # noqa: E402

DATASET = REPO_ROOT / "evals" / "datasets" / "mesh_scenarios_v1.jsonl"
REPORTS_DIR = REPO_ROOT / "evals" / "reports"
DATASET_VERSION = "v1"
TELEMETRY_PORT = 8941
TELEMETRY_URL = f"http://127.0.0.1:{TELEMETRY_PORT}"


def load_jsonl(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def start_telemetry_server() -> uvicorn.Server:
    config = uvicorn.Config(telemetry_app, host="127.0.0.1", port=TELEMETRY_PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            if httpx.get(f"{TELEMETRY_URL}/health", timeout=0.5).status_code == 200:
                return server
        except httpx.RequestError:
            time.sleep(0.2)
    raise RuntimeError("telemetry agent did not start in time")


def fresh_commander_client(tmp_dir: Path, case_id: str):
    os.environ["FIELDFORGE_MESH_COMMANDER_DB_PATH"] = str(tmp_dir / f"{case_id}.sqlite3")
    from fieldforge_mesh_commander import config as config_module

    importlib.reload(config_module)
    from fieldforge_mesh_commander import main as main_module

    importlib.reload(main_module)
    return TestClient(main_module.app), main_module


def run_case(case: dict, tmp_dir: Path) -> dict:
    client, main_module = fresh_commander_client(tmp_dir, case["id"])
    start = time.perf_counter()
    result = {"id": case["id"], "type": case["type"], "pass": False, "detail": {}}

    try:
        if case["type"] == "delegation":
            client.post("/agents/discover", json={"endpoint": TELEMETRY_URL})
            resp = client.post("/incidents", json=case["input"])
            report = resp.json()
            ok = (
                resp.status_code == 201
                and report["safety_decision"] == case["expected_safety_decision"]
                and report["disagreement_flag"] == case["expected_disagreement_flag"]
            )
            result["pass"] = ok
            result["detail"] = {
                "safety_decision": report.get("safety_decision"),
                "disagreement_flag": report.get("disagreement_flag"),
            }

        elif case["type"] == "no_analyst_registered":
            resp = client.post("/incidents", json=case["input"])
            report = resp.json()
            ok = (
                resp.status_code == 201
                and "degraded_no_analyst_evidence" in report["safety_decision"]
                and report["requires_human_approval"] is True
            )
            result["pass"] = ok
            result["detail"] = {"safety_decision": report.get("safety_decision")}

        elif case["type"] == "unreachable_analyst":
            bad_card = {
                "id": "telemetry-analyst",
                "name": "Telemetry Analyst",
                "role": "telemetry-analyst",
                "capabilities": [],
                "supported_task_types": ["investigate_telemetry"],
                "auth_required": True,
                "endpoint": "http://127.0.0.1:1",
            }
            client.post("/agents/register", json=bad_card)
            resp = client.post("/incidents", json=case["input"])
            report = resp.json()
            ok = resp.status_code == 201 and "degraded_no_analyst_evidence" in report["safety_decision"]
            result["pass"] = ok
            result["detail"] = {"safety_decision": report.get("safety_decision")}

        elif case["type"] == "unsupported_task_type":
            fake_card = {
                "id": "telemetry-analyst",
                "name": "Fake Telemetry Analyst",
                "role": "telemetry-analyst",
                "capabilities": [],
                "supported_task_types": [],
                "auth_required": True,
                "endpoint": TELEMETRY_URL,
            }
            client.post("/agents/register", json=fake_card)
            resp = client.post("/incidents", json=case["input"])
            report = resp.json()
            ok = (
                resp.status_code == 201
                and "degraded_no_analyst_evidence" in report["safety_decision"]
                and "does not support" in (report.get("error") or "")
            )
            result["pass"] = ok
            result["detail"] = {"error": report.get("error")}

        elif case["type"] == "unknown_device":
            client.post("/agents/discover", json={"endpoint": TELEMETRY_URL})
            resp = client.post("/incidents", json=case["input"])
            report = resp.json()
            ok = resp.status_code == 201 and "degraded_no_analyst_evidence" in report["safety_decision"]
            result["pass"] = ok
            result["detail"] = {"safety_decision": report.get("safety_decision")}

        elif case["type"] == "agent_card_correctness":
            resp = client.post("/agents/discover", json={"endpoint": TELEMETRY_URL})
            card = resp.json()
            ok = (
                resp.status_code == 201
                and card["id"]
                and card["role"] == "telemetry-analyst"
                and len(card["capabilities"]) > 0
                and "investigate_telemetry" in card["supported_task_types"]
            )
            result["pass"] = ok
            result["detail"] = {"id": card.get("id"), "capabilities": len(card.get("capabilities", []))}

        elif case["type"] == "message_exchange_validity":
            client.post("/agents/discover", json={"endpoint": TELEMETRY_URL})
            client.post("/incidents", json=case["input"])
            tclient = TestClient(telemetry_app)
            tasks = tclient.get("/tasks").json()
            last_task = tasks[-1] if tasks else None
            ok = bool(
                last_task
                and len(last_task["messages"]) >= 2
                and last_task["messages"][0]["role"] == "requester"
                and last_task["messages"][1]["role"] == "agent"
            )
            result["pass"] = ok
            result["detail"] = {"message_count": len(last_task["messages"]) if last_task else 0}

        elif case["type"] == "malformed_discovery":
            resp = client.post("/agents/discover", json=case["input"])
            ok = resp.status_code == case["expected_http_status"]
            result["pass"] = ok
            result["detail"] = {"http_status": resp.status_code}

        else:
            raise ValueError(f"unknown scenario type: {case['type']}")
    finally:
        main_module.store.close()

    result["latency_ms"] = round((time.perf_counter() - start) * 1000, 3)
    return result


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    cases = load_jsonl(DATASET)

    server = start_telemetry_server()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            results = [run_case(case, Path(tmp)) for case in cases]
    finally:
        server.should_exit = True

    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    delegation = [r for r in results if r["type"] == "delegation"]
    degradation_types = (
        "no_analyst_registered",
        "unreachable_analyst",
        "unsupported_task_type",
        "unknown_device",
    )
    degradation = [r for r in results if r["type"] in degradation_types]
    discovery = [r for r in results if r["type"] in ("agent_card_correctness", "malformed_discovery")]
    latencies = sorted(r["latency_ms"] for r in results)

    def _rate(subset: list[dict]) -> float:
        return round(sum(1 for r in subset if r["pass"]) / len(subset), 3) if subset else 0.0

    def _pct(values: list[float], pct: float) -> float:
        if not values:
            return 0.0
        idx = min(len(values) - 1, int(round(pct / 100 * (len(values) - 1))))
        return round(values[idx], 3)

    report = {
        "dataset_id": "mesh_scenarios_v1",
        "dataset_version": DATASET_VERSION,
        "case_count": total,
        "goal_completion_rate": round(passed / total, 3) if total else 0.0,
        "delegation_accuracy": _rate(delegation),
        "graceful_degradation_rate": _rate(degradation),
        "agent_discovery_success_rate": _rate(discovery),
        "latency_ms_p50": _pct(latencies, 50),
        "latency_ms_p95": _pct(latencies, 95),
        "detail": results,
        "limitations": (
            "11 hand-authored scenarios over 2 real, separately-deployed agents; not the "
            "40-scenario suite the program brief specifies for Mesh — see docs/ROADMAP.md. "
            "Conflict preservation is demonstrated within one analyst's two independent "
            "signals (rule-based + model-based), not across two independent agents — see "
            "docs/adr/0003-mesh-agent-protocol.md decision 5."
        ),
    }

    (REPORTS_DIR / "mesh_scenarios_v1_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    print("=== FieldForge Mesh — Slice 1 Evaluation ===")
    for key in (
        "case_count",
        "goal_completion_rate",
        "delegation_accuracy",
        "graceful_degradation_rate",
        "agent_discovery_success_rate",
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
