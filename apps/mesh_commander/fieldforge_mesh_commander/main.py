"""FieldForge Mesh — Incident Commander agent.

Discovers peer agents over a real HTTP call to their /.well-known/agent-card,
delegates investigation tasks over A2A, applies Safety Officer policy, and produces
a MeshIncidentReport that always requires human approval — Commander delegates but
never executes (docs/adr/0003-mesh-agent-protocol.md decision 4, program brief's
Mesh permission matrix).
"""

from __future__ import annotations

import logging

import httpx
from fastapi import FastAPI, HTTPException
from fieldforge_contracts import (
    A2ATaskStatus,
    AgentCard,
    AnalystFinding,
    DelegationRecord,
    MeshIncidentReport,
)
from fieldforge_observability import configure_json_logging, get_correlation_id, new_trace_id
from pydantic import BaseModel

from fieldforge_mesh_commander import safety_officer
from fieldforge_mesh_commander.config import settings
from fieldforge_mesh_commander.delegation import DelegationError, delegate_task
from fieldforge_mesh_commander.middleware import CorrelationIdMiddleware
from fieldforge_mesh_commander.registry import AgentRegistry
from fieldforge_mesh_commander.store import MeshIncidentStore

configure_json_logging()
logger = logging.getLogger("fieldforge.mesh_commander")

app = FastAPI(
    title="FieldForge Mesh — Incident Commander",
    version="0.1.0",
    description="Discovers agents, delegates investigation over A2A, applies safety policy.",
)
app.add_middleware(CorrelationIdMiddleware)

registry = AgentRegistry()
store = MeshIncidentStore(settings.db_path)


@app.on_event("shutdown")
def _shutdown() -> None:
    store.close()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "registered_agents": len(registry.list()), "incidents": len(store.list())}


@app.post("/agents/register", status_code=201)
def register_agent(card: AgentCard) -> AgentCard:
    registry.register(card)
    return card


class DiscoverBody(BaseModel):
    endpoint: str


@app.post("/agents/discover", status_code=201)
def discover_agent(body: DiscoverBody) -> AgentCard:
    try:
        resp = httpx.get(f"{body.endpoint}/.well-known/agent-card", timeout=5.0)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"could not reach {body.endpoint}: {exc}") from exc
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"agent-card fetch returned {resp.status_code}")
    try:
        card = AgentCard.model_validate(resp.json())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"malformed agent card: {exc}") from exc
    # Trust the address we actually reached the agent at, not its self-reported
    # endpoint field — a peer's own config can be stale or wrong for the network
    # it's actually reachable on (e.g. a different port in a test/deployment than
    # its default config assumes). Found via a real test failure: see
    # tests/integration/test_mesh_commander_api.py.
    card = card.model_copy(update={"endpoint": body.endpoint})
    registry.register(card)
    return card


@app.get("/agents")
def list_agents() -> list[AgentCard]:
    return registry.list()


@app.get("/incidents")
def list_incidents() -> list[MeshIncidentReport]:
    return store.list()


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> MeshIncidentReport:
    report = store.get(incident_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"incident {incident_id} not found")
    return report


class InvestigateBody(BaseModel):
    device_id: str
    value: float
    triggered_at: str
    window_seconds: float
    corroborating_device_id: str | None = None


@app.post("/incidents", status_code=201)
def investigate(body: InvestigateBody) -> MeshIncidentReport:
    trace_id = get_correlation_id() or new_trace_id()
    delegation_log: list[DelegationRecord] = []

    analyst = registry.find_by_role("telemetry-analyst")
    if analyst is None:
        report = MeshIncidentReport(
            device_id=body.device_id,
            corroborating_device_id=body.corroborating_device_id,
            safety_decision="degraded_no_analyst_evidence: no telemetry-analyst agent registered",
            requires_human_approval=True,
            error="no telemetry-analyst agent registered; call POST /agents/discover first",
            trace_id=trace_id,
        )
        store.save(report)
        return report

    task_input = {
        "device_id": body.device_id,
        "value": body.value,
        "triggered_at": body.triggered_at,
        "window_seconds": body.window_seconds,
        "corroborating_device_id": body.corroborating_device_id,
    }

    finding: AnalystFinding | None = None
    analyst_error: str | None = None
    try:
        task, duration_ms = delegate_task(
            analyst,
            "investigate_telemetry",
            task_input,
            settings.agent_token,
            settings.delegation_timeout_seconds,
        )
        delegation_log.append(
            DelegationRecord(
                agent_id=analyst.id,
                task_id=task.id,
                task_type=task.task_type,
                status=task.status,
                duration_ms=duration_ms,
            )
        )
        if task.status == A2ATaskStatus.COMPLETED and task.artifacts:
            finding = AnalystFinding.model_validate(task.artifacts[0].content)
        else:
            analyst_error = task.error or "analyst task did not complete"
    except DelegationError as exc:
        analyst_error = str(exc)
        delegation_log.append(
            DelegationRecord(
                agent_id=analyst.id,
                task_id="none",
                task_type="investigate_telemetry",
                status=A2ATaskStatus.FAILED,
                duration_ms=0.0,
            )
        )

    safety_decision, requires_approval = safety_officer.decide(finding, analyst_error)

    report = MeshIncidentReport(
        device_id=body.device_id,
        corroborating_device_id=body.corroborating_device_id,
        analyst_finding=finding,
        safety_decision=safety_decision,
        requires_human_approval=requires_approval,
        disagreement_flag=(finding is not None and not finding.signals_agree),
        delegation_log=delegation_log,
        error=analyst_error if finding is None else None,
        trace_id=trace_id,
    )
    store.save(report)

    logger.info(
        "incident investigated",
        extra={
            "extra_fields": {
                "trace_id": trace_id,
                "incident_id": report.id,
                "safety_decision": safety_decision,
                "disagreement_flag": report.disagreement_flag,
            }
        },
    )
    return report
