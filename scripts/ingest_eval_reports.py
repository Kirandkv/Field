"""Ingests the real evaluation reports and baselines already produced by
scripts/run_eval.py, run_copilot_eval.py, and run_mesh_eval.py into a running
FieldForge Ops instance, then runs the quality gate for each dataset.

This is real ingestion of real data — nothing here is fabricated. Run the other
three products' eval scripts first so evals/reports/ is up to date.

Usage:
    uvicorn fieldforge_ops_api.main:app --port 8030 &
    python scripts/ingest_eval_reports.py --ops-url http://localhost:8030
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINES_DIR = REPO_ROOT / "evals" / "baselines"
REPORTS_DIR = REPO_ROOT / "evals" / "reports"

NON_METRIC_KEYS = {"dataset_id", "dataset_version", "case_count", "detail", "limitations"}

# (baseline filename, report filename, dataset_id, dataset_version, product)
DATASETS = [
    ("docs_v1_baseline.json", "docs_qa_v1_report.json", "docs_qa_v1", "v1", "docs"),
    ("guardrails_v1_baseline.json", "guardrails_docs_v1_report.json", "guardrails_docs_v1", "v1", "docs"),
    (
        "copilot_scenarios_v1_baseline.json",
        "copilot_scenarios_v1_report.json",
        "copilot_scenarios_v1",
        "v1",
        "copilot",
    ),
    ("mesh_scenarios_v1_baseline.json", "mesh_scenarios_v1_report.json", "mesh_scenarios_v1", "v1", "mesh"),
]


def _metrics_from(data: dict) -> dict[str, float | str]:
    return {k: v for k, v in data.items() if k not in NON_METRIC_KEYS}


def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def ingest(ops_url: str) -> int:
    client = httpx.Client(base_url=ops_url, timeout=10.0)
    ingested = 0
    gated = 0

    for baseline_file, report_file, dataset_id, dataset_version, product in DATASETS:
        baseline_data = _load(BASELINES_DIR / baseline_file)
        report_data = _load(REPORTS_DIR / report_file)

        if baseline_data is not None:
            resp = client.post(
                "/evaluations",
                json={
                    "product": product,
                    "dataset_id": dataset_id,
                    "dataset_version": dataset_version,
                    "case_count": baseline_data.get("case_count", 0),
                    "metrics": _metrics_from(baseline_data),
                    "is_baseline": True,
                    "source": f"evals/baselines/{baseline_file}",
                },
            )
            resp.raise_for_status()
            ingested += 1
            print(f"ingested baseline: {product}/{dataset_id}")

        if report_data is not None:
            resp = client.post(
                "/evaluations",
                json={
                    "product": product,
                    "dataset_id": dataset_id,
                    "dataset_version": dataset_version,
                    "case_count": report_data.get("case_count", 0),
                    "metrics": _metrics_from(report_data),
                    "is_baseline": False,
                    "source": f"evals/reports/{report_file}",
                },
            )
            resp.raise_for_status()
            ingested += 1
            print(f"ingested current run: {product}/{dataset_id}")

        if baseline_data is not None and report_data is not None:
            gate_resp = client.post("/quality-gate/run", json={"product": product, "dataset_id": dataset_id})
            gate_resp.raise_for_status()
            gate = gate_resp.json()
            gated += 1
            print(f"quality gate {product}/{dataset_id}: {gate['decision']}")

    print(f"\n{ingested} evaluation run(s) ingested, {gated} quality gate(s) run")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ops-url", default="http://localhost:8030")
    args = parser.parse_args()
    try:
        sys.exit(ingest(args.ops_url))
    except httpx.RequestError as exc:
        print(f"ERROR: could not reach Ops API at {args.ops_url}: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
