from __future__ import annotations

import logging

from fastapi import FastAPI, Header, HTTPException
from fieldforge_agent_copilot.orchestrator import investigate
from fieldforge_agent_copilot.state_machine import AgentStateMachine, InvalidTransitionError
from fieldforge_anomaly import DeviceAnomalyDetector
from fieldforge_contracts import (
    Alert,
    ApprovalDecision,
    ApprovalDecisionType,
    ApprovalRequest,
    Incident,
    IncidentState,
    MaintenanceTicket,
    Role,
)
from fieldforge_observability import configure_json_logging, get_correlation_id, new_trace_id
from fieldforge_telemetry import TelemetryStore
from pydantic import BaseModel

from fieldforge_copilot_api.config import settings
from fieldforge_copilot_api.middleware import CorrelationIdMiddleware
from fieldforge_copilot_api.store import CopilotStore

configure_json_logging()
logger = logging.getLogger("fieldforge.copilot_api")

app = FastAPI(
    title="FieldForge Copilot API",
    version="0.1.0",
    description=(
        "Single human-supervised agent investigating FieldForge Industries incidents. "
        "Slice 1: one flagship methane-incident scenario, explicit state machine, "
        "human approval required for every state-changing action."
    ),
)
app.add_middleware(CorrelationIdMiddleware)

telemetry_store = TelemetryStore()
detector = DeviceAnomalyDetector()
for _device_id in ("FF-R07", "FIX-B3-02", "FIX-B3-01"):
    _values = [p.value for p in telemetry_store.get_history(_device_id)]
    detector.fit(_device_id, _values)

store = CopilotStore(settings.db_path)


@app.on_event("shutdown")
def _shutdown() -> None:
    store.close()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "incidents": len(store.list_incidents()),
        "pending_approvals": len(store.list_pending_approvals()),
        "docs_api_url": settings.docs_api_url,
    }


@app.get("/incidents")
def list_incidents() -> list[Incident]:
    return store.list_incidents()


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> Incident:
    incident = store.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"incident {incident_id} not found")
    return incident


@app.post("/alerts", status_code=201)
def submit_alert(alert: Alert) -> Incident:
    trace_id = get_correlation_id() or new_trace_id()
    incident, approval = investigate(alert, telemetry_store, detector, docs_api_url=settings.docs_api_url)
    incident.trace_id = trace_id
    store.save_incident(incident)
    if approval is not None:
        store.save_approval_request(approval)
    logger.info(
        "incident investigated",
        extra={
            "extra_fields": {
                "trace_id": trace_id,
                "incident_id": incident.id,
                "state": incident.state.value,
                "classification": incident.classification.value if incident.classification else None,
            }
        },
    )
    return incident


@app.post("/demo/scenarios/{scenario_id}/trigger", status_code=201)
def trigger_demo_scenario(scenario_id: str) -> Incident:
    """Convenience endpoint over the canned scenarios in data/samples/telemetry/alerts.json
    — lets a reviewer exercise the flagship demo without hand-building an Alert payload.
    """
    scenarios = {s["id"]: s for s in telemetry_store.list_alert_scenarios()}
    if scenario_id not in scenarios:
        raise HTTPException(status_code=404, detail=f"unknown demo scenario {scenario_id!r}")
    s = scenarios[scenario_id]
    alert = Alert(
        device_id=s["device_id"],
        metric=s["metric"],
        value=s["value"],
        window_seconds=s["window_seconds"],
        triggered_at=s["triggered_at"],
        corroborating_device_id=s.get("corroborating_device_id"),
    )
    return submit_alert(alert)


@app.get("/approvals")
def list_pending_approvals() -> list[ApprovalRequest]:
    return store.list_pending_approvals()


@app.get("/approvals/{approval_id}")
def get_approval(approval_id: str) -> ApprovalRequest:
    approval = store.get_approval_request(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail=f"approval request {approval_id} not found")
    return approval


class DecisionRequest(BaseModel):
    decision: ApprovalDecisionType
    modified_arguments: dict | None = None
    reason: str | None = None


@app.post("/approvals/{approval_id}/decision")
def decide_approval(
    approval_id: str,
    body: DecisionRequest,
    x_fieldforge_role: str | None = Header(default=None),
) -> Incident:
    # Backend enforcement, not a UI suggestion — see ADR 0002 decision 4. Only Safety
    # Manager may approve, reject, or modify-and-approve a proposed action.
    if x_fieldforge_role != Role.SAFETY_MANAGER.value:
        raise HTTPException(
            status_code=403,
            detail=f"approval decisions require role={Role.SAFETY_MANAGER.value}, got {x_fieldforge_role!r}",
        )

    approval = store.get_approval_request(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail=f"approval request {approval_id} not found")
    if approval.decided:
        raise HTTPException(status_code=409, detail=f"approval request {approval_id} already decided")

    incident = store.get_incident(approval.incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"incident {approval.incident_id} not found")

    decision = ApprovalDecision(
        approval_request_id=approval.id,
        approver_role=Role.SAFETY_MANAGER,
        decision=body.decision,
        modified_arguments=body.modified_arguments,
        reason=body.reason,
    )

    try:
        if body.decision == ApprovalDecisionType.REJECT:
            incident.state = AgentStateMachine.transition(incident.state, IncidentState.REJECTED)
        else:
            arguments = body.modified_arguments or approval.proposed_action.arguments
            incident.state = AgentStateMachine.transition(
                incident.state, IncidentState.EXECUTING_APPROVED_ACTION
            )
            ticket = MaintenanceTicket(
                incident_id=incident.id,
                device_id=arguments["device_id"],
                description=arguments["description"],
                approved_by=f"role:{Role.SAFETY_MANAGER.value}",
            )
            store.save_ticket(ticket)
            incident.state = AgentStateMachine.transition(incident.state, IncidentState.VERIFYING)
            incident.state = AgentStateMachine.transition(incident.state, IncidentState.COMPLETED)
    except InvalidTransitionError as exc:
        incident.state = IncidentState.FAILED
        incident.error = str(exc)
        store.save_incident(incident)
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    approval.decided = True
    store.save_approval_request(approval)
    store.save_approval_decision(decision)
    store.save_incident(incident)
    return incident


@app.get("/tickets")
def list_tickets() -> list[MaintenanceTicket]:
    return store.list_tickets()
