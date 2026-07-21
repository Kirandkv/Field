"""Runs one incident investigation through the explicit state machine, RECEIVED
through either AWAITING_APPROVAL or a terminal state (REQUESTING_MORE_EVIDENCE,
FAILED). Execution of an approved action (AWAITING_APPROVAL onward) is a separate
step, triggered only by a real human decision reaching apps/copilot_api — this
module never executes a state-changing tool itself.

The classification policy below implements SOP-014 as written in the FieldForge Docs
corpus (data/samples/sop_methane_survey_response.md): corroboration against a second
device is mandatory, and disagreement or missing corroborating data is treated as
insufficient evidence rather than resolved by guessing.
"""

from __future__ import annotations

from fieldforge_anomaly import DeviceAnomalyDetector
from fieldforge_contracts import (
    Alert,
    AlertSeverity,
    ApprovalRequest,
    DataQualityFlag,
    Evidence,
    EvidenceKind,
    Incident,
    IncidentClassification,
    IncidentState,
    RiskLevel,
    SensorMetric,
    TelemetryPoint,
    ToolResult,
)
from fieldforge_telemetry import TelemetryStore

from fieldforge_agent_copilot import tools
from fieldforge_agent_copilot.state_machine import AgentStateMachine

HIGH_SEVERITY_PPM = 1000
HIGH_SEVERITY_MIN_WINDOW_S = 30
MEDIUM_SEVERITY_PPM = 500
CORROBORATION_ELEVATED_PPM = 100

# Fixed sensors in the synthetic corpus sample every 10 minutes (see
# data/generators/generate_telemetry.py), not continuously — searching only the
# primary device's own (much shorter) spike window would almost always find zero
# corroborating points by pure sampling-alignment bad luck, not because the data is
# actually missing. A wider corroboration window (with margin over the 5-minute
# worst-case gap to the nearest sample) reflects how a real fixed-interval sensor's
# "reading for this window" is actually determined.
MIN_CORROBORATION_HALF_WIDTH_S = 700


def _triage(alert: Alert) -> AlertSeverity:
    if alert.value > HIGH_SEVERITY_PPM and alert.window_seconds >= HIGH_SEVERITY_MIN_WINDOW_S:
        return AlertSeverity.HIGH
    if alert.value > MEDIUM_SEVERITY_PPM:
        return AlertSeverity.MEDIUM
    return AlertSeverity.LOW


def investigate(
    alert: Alert,
    store: TelemetryStore,
    detector: DeviceAnomalyDetector,
    docs_api_url: str = tools.DEFAULT_DOCS_API_URL,
) -> tuple[Incident, ApprovalRequest | None]:
    incident = Incident(alert=alert, state=IncidentState.RECEIVED)
    sm = AgentStateMachine

    incident.state = sm.transition(incident.state, IncidentState.TRIAGING)
    incident.severity = _triage(alert)

    incident.state = sm.transition(incident.state, IncidentState.COLLECTING_EVIDENCE)

    device_result = tools.get_device(store, alert.device_id)
    if not device_result.ok:
        incident.state = sm.transition(incident.state, IncidentState.FAILED)
        incident.error = device_result.error
        return incident, None

    primary_history = tools.get_sensor_history(
        store, alert.device_id, alert.triggered_at, alert.window_seconds
    )
    primary_points = primary_history.data["points"]
    primary_summary = tools.summarize_telemetry_window(
        [_point_from_dict(p) for p in primary_points]
    )
    incident.evidence.append(
        Evidence(
            kind=EvidenceKind.TELEMETRY,
            source_id=alert.device_id,
            summary=f"{alert.device_id} window summary: {primary_summary.data}",
            data=primary_summary.data,
            confidence=1.0,
            producing_component="summarize_telemetry_window",
        )
    )

    anomaly_result = tools.run_isolation_forest(detector, alert.device_id, alert.value)
    if anomaly_result.ok:
        incident.evidence.append(
            Evidence(
                kind=EvidenceKind.ANOMALY_SCORE,
                source_id=alert.device_id,
                summary=(
                    f"Isolation Forest: is_anomaly={anomaly_result.data['is_anomaly']} "
                    f"score={anomaly_result.data['anomaly_score']} "
                    f"(fit on {anomaly_result.data['training_samples']} historical readings)"
                ),
                data=anomaly_result.data,
                confidence=0.6,  # a single-metric model's opinion, not corroboration-grade
                producing_component="run_isolation_forest",
            )
        )

    sop_result = tools.retrieve_sop(
        "methane survey alert response corroboration procedure", docs_api_url=docs_api_url
    )
    if sop_result.ok and not sop_result.data.get("refused"):
        for citation in sop_result.data["citations"][:2]:
            incident.evidence.append(
                Evidence(
                    kind=EvidenceKind.SOP_CITATION,
                    source_id=citation["source_id"],
                    summary=citation["quote"],
                    data={},
                    confidence=citation["confidence"],
                    retrieval_score=citation["retrieval_score"],
                    page_number=citation["page_number"],
                    producing_component="retrieve_sop (FieldForge Docs)",
                )
            )

    corroborating_summary: ToolResult | None = None
    if alert.corroborating_device_id:
        corr_half_width = max(alert.window_seconds, MIN_CORROBORATION_HALF_WIDTH_S)
        corr_history = tools.get_sensor_history(
            store, alert.corroborating_device_id, alert.triggered_at, corr_half_width
        )
        corroborating_summary = tools.summarize_telemetry_window(
            [_point_from_dict(p) for p in corr_history.data["points"]]
        )
        incident.evidence.append(
            Evidence(
                kind=EvidenceKind.TELEMETRY,
                source_id=alert.corroborating_device_id,
                summary=(
                    f"{alert.corroborating_device_id} (corroborating) window summary: "
                    f"{corroborating_summary.data}"
                ),
                data=corroborating_summary.data,
                confidence=1.0,
                producing_component="summarize_telemetry_window",
            )
        )

    incident.state = sm.transition(incident.state, IncidentState.ANALYZING)

    insufficient_reason = _insufficient_evidence_reason(alert, corroborating_summary)
    if insufficient_reason:
        incident.classification = IncidentClassification.INSUFFICIENT_EVIDENCE
        incident.reasoning_summary = (
            f"{alert.device_id} reported {alert.value} ppm sustained {alert.window_seconds}s. "
            f"{insufficient_reason} Per SOP-014, this must be classified as insufficient "
            f"evidence rather than resolved either way — see evidence list."
        )
        incident.state = sm.transition(incident.state, IncidentState.REQUESTING_MORE_EVIDENCE)
        return incident, None

    corr_max = corroborating_summary.data["max"] if corroborating_summary else 0.0
    if corr_max > CORROBORATION_ELEVATED_PPM:
        incident.classification = IncidentClassification.LIKELY_REAL_EVENT
        risk = RiskLevel.HIGH
        description = (
            f"Both {alert.device_id} ({alert.value} ppm) and {alert.corroborating_device_id} "
            f"({corr_max} ppm peak) show elevated methane readings for the same window. "
            f"Escalate to Safety Manager; do not dispatch personnel without sign-off (SOP-014)."
        )
    else:
        incident.classification = IncidentClassification.LIKELY_SENSOR_FAULT
        risk = RiskLevel.MEDIUM
        description = (
            f"{alert.device_id} reported {alert.value} ppm but corroborating device "
            f"{alert.corroborating_device_id} stayed normal (peak {corr_max} ppm) for the "
            f"same window. Likely sensor fault per SOP-014; recommend bench recalibration. "
            f"Incident cannot be closed without Safety Manager review."
        )

    incident.reasoning_summary = description
    incident.state = sm.transition(incident.state, IncidentState.PROPOSING_ACTION)

    draft = tools.draft_maintenance_ticket(
        device_id=alert.device_id,
        description=description,
        risk_level=risk,
        estimated_impact="No physical action taken; creates a scheduling/escalation record only.",
        alternatives=[
            "Reject and request additional telemetry before any ticket is created",
            "Modify ticket description before approving",
        ],
    )
    proposed_action = draft.data["proposed_action"]

    incident.state = sm.transition(incident.state, IncidentState.AWAITING_APPROVAL)
    approval = ApprovalRequest(
        incident_id=incident.id,
        proposed_action=proposed_action,
        reasoning_summary=description,
        evidence_ids=[e.id for e in incident.evidence],
        risk_level=risk,
    )
    return incident, approval


def _insufficient_evidence_reason(alert: Alert, corroborating_summary: ToolResult | None) -> str | None:
    if not alert.corroborating_device_id:
        return "No corroborating device is configured for this alert."
    if corroborating_summary is None or not corroborating_summary.data.get("has_data"):
        return f"No corroborating telemetry available from {alert.corroborating_device_id} for this window."
    if corroborating_summary.data.get("has_stale_reading"):
        return f"Corroborating device {alert.corroborating_device_id}'s data for this window is stale."
    return None


def _point_from_dict(raw: dict) -> TelemetryPoint:
    return TelemetryPoint(
        device_id=raw["device_id"],
        metric=SensorMetric(raw["metric"]),
        value=raw["value"],
        timestamp=raw["timestamp"],
        quality_flag=DataQualityFlag(raw["quality_flag"]),
    )
