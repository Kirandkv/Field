"""FieldForge Mesh — Telemetry Analyst agent.

A2A-shaped HTTP surface (docs/adr/0003-mesh-agent-protocol.md decision 2) wrapping
the same tool implementations telemetry-mcp exposes over MCP
(services/mcp_telemetry/fieldforge_mcp_telemetry/core.py) — one implementation, two
transports.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import FastAPI, Header, HTTPException
from fieldforge_anomaly import DeviceAnomalyDetector
from fieldforge_contracts import (
    A2AArtifact,
    A2AMessage,
    A2ATask,
    A2ATaskStatus,
    AgentCapability,
    AgentCard,
)
from fieldforge_mcp_telemetry import core
from fieldforge_observability import configure_json_logging, get_correlation_id, new_trace_id
from fieldforge_telemetry import TelemetryStore

from fieldforge_mesh_telemetry_agent.config import settings
from fieldforge_mesh_telemetry_agent.middleware import CorrelationIdMiddleware
from fieldforge_mesh_telemetry_agent.task_store import TaskStore

configure_json_logging()
logger = logging.getLogger("fieldforge.mesh_telemetry_agent")

app = FastAPI(
    title="FieldForge Mesh — Telemetry Analyst",
    version="0.1.0",
    description="Read-only telemetry investigation agent, reachable over A2A and MCP.",
)
app.add_middleware(CorrelationIdMiddleware)

store = TelemetryStore()
detector = DeviceAnomalyDetector()
for _device in store.list_devices():
    _values = [p.value for p in store.get_history(_device.id)]
    if len(_values) >= 10:
        detector.fit(_device.id, _values)

tasks = TaskStore()

AGENT_ID = "telemetry-analyst"
SUPPORTED_TASK_TYPES = ["investigate_telemetry"]


def _agent_card() -> AgentCard:
    return AgentCard(
        id=AGENT_ID,
        name="Telemetry Analyst",
        role="telemetry-analyst",
        capabilities=[
            AgentCapability(
                task_type="investigate_telemetry",
                description=(
                    "Compare a device's reading against a corroborating device and score it "
                    "against the device's own Isolation Forest anomaly model."
                ),
                input_schema={
                    "device_id": "str",
                    "value": "float",
                    "triggered_at": "ISO 8601 str",
                    "window_seconds": "float",
                    "corroborating_device_id": "str | null",
                },
                output_schema={"artifact": "AnalystFinding"},
            )
        ],
        supported_task_types=SUPPORTED_TASK_TYPES,
        auth_required=True,
        endpoint=settings.self_endpoint,
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "agent_id": AGENT_ID, "task_count": len(tasks.list())}


@app.get("/.well-known/agent-card")
def agent_card() -> AgentCard:
    return _agent_card()


@app.get("/tasks")
def list_tasks() -> list[A2ATask]:
    return tasks.list()


@app.get("/tasks/{task_id}")
def get_task(task_id: str) -> A2ATask:
    task = tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task {task_id} not found")
    return task


@app.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str) -> A2ATask:
    task = tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task {task_id} not found")
    # Tasks in this slice complete synchronously within POST /tasks (ADR 0003
    # decision 6), so by the time a cancel request can arrive the task is already
    # terminal — report its real status rather than fabricating a cancellation.
    return task


@app.post("/tasks", status_code=201)
def create_task(body: dict, x_fieldforge_agent_token: str | None = Header(default=None)) -> A2ATask:
    if x_fieldforge_agent_token != settings.agent_token:
        raise HTTPException(status_code=403, detail="invalid or missing agent token")

    trace_id = get_correlation_id() or new_trace_id()
    task_type = body.get("task_type")
    task_input = body.get("input", {})

    if task_type not in SUPPORTED_TASK_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported task_type {task_type!r}; supported: {SUPPORTED_TASK_TYPES}",
        )

    required = {"device_id", "value", "triggered_at", "window_seconds"}
    missing = required - task_input.keys()
    if missing:
        raise HTTPException(status_code=400, detail=f"missing required input fields: {sorted(missing)}")

    task = A2ATask(
        task_type=task_type,
        input=task_input,
        status=A2ATaskStatus.WORKING,
        correlation_id=trace_id,
        messages=[A2AMessage(role="requester", content=f"investigate_telemetry: {task_input}")],
    )

    device_id = task_input["device_id"]
    value = float(task_input["value"])
    corroborating_device_id = task_input.get("corroborating_device_id")
    try:
        center = datetime.fromisoformat(task_input["triggered_at"])
    except ValueError as exc:
        task.status = A2ATaskStatus.FAILED
        task.error = f"invalid triggered_at: {exc}"
        tasks.save(task)
        return task
    window_seconds = float(task_input["window_seconds"])

    if store.get_device(device_id) is None:
        task.status = A2ATaskStatus.FAILED
        task.error = f"unknown device {device_id!r}"
        tasks.save(task)
        return task

    if corroborating_device_id:
        comparison = core.compare_devices(store, device_id, corroborating_device_id, center, window_seconds)
        rule_based = comparison["rule_based_classification"]
        corr_summary = comparison["corroborating_summary"]
        primary_summary = comparison["primary_summary"]
    else:
        query = core.query_telemetry(store, device_id, center, window_seconds)
        rule_based = "insufficient_evidence"
        corr_summary = None
        primary_summary = query["summary"]

    anomaly = core.run_anomaly_detection(detector, device_id, value)
    model_is_anomaly = anomaly.get("is_anomaly", False)
    # Two independent signals are reported, not collapsed — see ADR 0003 decision 5.
    # "Agreement" here means both signals point toward a real, corroborated concern:
    # the rule says a real event, or the rule says a sensor fault and the anomaly
    # model also flags the reading as statistically unusual (expected for a fault).
    signals_agree = (rule_based == "likely_real_event") or (
        rule_based == "likely_sensor_fault" and model_is_anomaly
    )

    finding = {
        "device_id": device_id,
        "corroborating_device_id": corroborating_device_id,
        "rule_based_classification": rule_based,
        "model_based_is_anomaly": model_is_anomaly,
        "signals_agree": signals_agree,
        "telemetry_summary": primary_summary,
        "corroborating_summary": corr_summary,
        "anomaly_summary": anomaly if anomaly.get("ok") else None,
    }

    task.artifacts = [A2AArtifact(name="analyst_finding", content=finding)]
    task.messages.append(
        A2AMessage(
            role="agent",
            content=f"classification={rule_based} model_is_anomaly={model_is_anomaly} agree={signals_agree}",
        )
    )
    task.status = A2ATaskStatus.COMPLETED
    tasks.save(task)

    logger.info(
        "task completed",
        extra={
            "extra_fields": {
                "trace_id": trace_id,
                "task_id": task.id,
                "task_type": task_type,
                "classification": rule_based,
            }
        },
    )
    return task
