"""Safety Officer policy: Incident Commander's in-process decision layer (see
docs/adr/0003-mesh-agent-protocol.md decision 4). Every branch requires human
approval — Commander can delegate investigation but never bypass approval and never
execute anything itself, the strictest permission boundary in the suite. Compare
FieldForge Copilot's orchestrator, which reaches the same classifications but is the
place where an approved action actually executes.
"""

from __future__ import annotations

from fieldforge_contracts import AnalystFinding


def decide(finding: AnalystFinding | None, analyst_error: str | None) -> tuple[str, bool]:
    """Returns (safety_decision, requires_human_approval). requires_human_approval
    is always True in this slice — see module docstring.
    """
    if finding is None:
        reason = analyst_error or "no analyst finding available"
        return f"degraded_no_analyst_evidence: {reason}", True

    if finding.rule_based_classification == "insufficient_evidence":
        return "insufficient_evidence_request_more_data", True

    if finding.rule_based_classification == "likely_real_event":
        return "escalate_immediately_to_safety_manager", True

    return "recommend_recalibration_pending_safety_review", True
