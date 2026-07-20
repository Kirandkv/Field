"""CI quality gate: fail the build if the guardrail adversarial eval regresses.

This is the one quality gate slice 1 ships with 100% as its threshold, because the
current adversarial set is small and hand-verified (see evals/datasets/guardrails_docs_v1.jsonl)
— any regression on it is real, not statistical noise. Other quality gates (retrieval
recall, faithfulness, latency) stay TBD until a large-enough baseline exists to set a
non-arbitrary threshold — see docs/EVALUATION_METHODOLOGY.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent.parent / "evals" / "reports"
REPORT_PATH = REPORTS_DIR / "guardrails_docs_v1_report.json"


def main() -> int:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    accuracy = report["accuracy"]
    if accuracy != 1.0:
        print(f"GATE FAILED: guardrail eval accuracy = {accuracy}, required 1.0")
        for case in report["detail"]:
            if not case["pass"]:
                print(f"  FAILED: {case}")
        return 1
    print(f"GATE PASSED: guardrail eval accuracy = {accuracy}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
