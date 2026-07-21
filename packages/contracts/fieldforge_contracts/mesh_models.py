"""Shared typed contracts for FieldForge Mesh (milestone M4).

A2A vocabulary (AgentCard, Task, Message, Artifact) follows the publicly documented
A2A protocol shape but is implemented independently — see
docs/adr/0003-mesh-agent-protocol.md decision 2. Kept in its own module, same
convention as copilot_models.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid.uuid4().hex


class AgentCapability(BaseModel):
    task_type: str
    description: str
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)


class AgentCard(BaseModel):
    """Identity + capability descriptor an agent publishes at
    GET /.well-known/agent-card — how a peer discovers what it can do.
    """

    id: str
    name: str
    role: str
    version: str = "0.1.0"
    capabilities: list[AgentCapability]
    supported_task_types: list[str]
    auth_required: bool = True
    endpoint: str
    status: str = "available"


class A2ATaskStatus(StrEnum):
    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class A2AMessage(BaseModel):
    role: str  # "requester" | "agent"
    content: str
    timestamp: datetime = Field(default_factory=_utcnow)


class A2AArtifact(BaseModel):
    id: str = Field(default_factory=_new_id)
    name: str
    content: dict = Field(default_factory=dict)


class A2ATask(BaseModel):
    id: str = Field(default_factory=_new_id)
    task_type: str
    input: dict
    status: A2ATaskStatus = A2ATaskStatus.SUBMITTED
    messages: list[A2AMessage] = Field(default_factory=list)
    artifacts: list[A2AArtifact] = Field(default_factory=list)
    error: str | None = None
    correlation_id: str = Field(default_factory=_new_id)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class AnalystFinding(BaseModel):
    """Telemetry Analyst's result for one device/window — deliberately carries two
    independent classifications rather than one, so disagreement between them is
    visible instead of collapsed. See ADR 0003 decision 5.
    """

    device_id: str
    corroborating_device_id: str | None
    rule_based_classification: str  # per SOP-014 corroboration policy
    model_based_is_anomaly: bool  # per Isolation Forest
    signals_agree: bool
    telemetry_summary: dict
    corroborating_summary: dict | None
    anomaly_summary: dict | None


class DelegationRecord(BaseModel):
    agent_id: str
    task_id: str
    task_type: str
    status: A2ATaskStatus
    duration_ms: float


class MeshIncidentReport(BaseModel):
    id: str = Field(default_factory=_new_id)
    device_id: str
    corroborating_device_id: str | None
    analyst_finding: AnalystFinding | None = None
    safety_decision: str  # e.g. "escalate_for_human_review", "insufficient_evidence", "degraded_no_analyst"
    requires_human_approval: bool = True
    disagreement_flag: bool = False
    delegation_log: list[DelegationRecord] = Field(default_factory=list)
    error: str | None = None
    trace_id: str = Field(default_factory=_new_id)
    created_at: datetime = Field(default_factory=_utcnow)
