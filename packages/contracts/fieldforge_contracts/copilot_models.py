"""Shared typed contracts for FieldForge Copilot (milestone M3).

Kept in a separate module from models.py (Docs' contracts) so each product's schema
surface stays readable on its own — see docs/adr/0002-copilot-agent-architecture.md.
Mesh/Ops contracts (AgentMessage, ToolRequest as a standalone A2A envelope,
TraceReference, ModelRun) are added when those milestones start.
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


class Role(StrEnum):
    """Suite-wide role enum. Enforced today only on Copilot's approval endpoint —
    see ADR 0002 decision 4. Full cross-product RBAC is planned for M2.
    """

    VIEWER = "viewer"
    OPERATOR = "operator"
    ENGINEER = "engineer"
    SAFETY_MANAGER = "safety_manager"
    ADMINISTRATOR = "administrator"


class DeviceType(StrEnum):
    MOBILE_ROBOT = "mobile_robot"
    FIXED_SENSOR = "fixed_sensor"


class Device(BaseModel):
    id: str
    name: str
    device_type: DeviceType
    site: str
    status: str = "active"


class SensorMetric(StrEnum):
    METHANE_PPM = "methane_ppm"
    # temperature/pressure/vibration/battery/network metrics are planned (M2) —
    # slice 1 implements exactly the metric the flagship scenario needs.


class DataQualityFlag(StrEnum):
    OK = "ok"
    STALE = "stale"
    SUSPECT_FAULT = "suspect_fault"


class TelemetryPoint(BaseModel):
    id: str = Field(default_factory=_new_id)
    device_id: str
    metric: SensorMetric
    value: float
    timestamp: datetime
    quality_flag: DataQualityFlag = DataQualityFlag.OK


class AlertSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Alert(BaseModel):
    id: str = Field(default_factory=_new_id)
    device_id: str
    metric: SensorMetric
    value: float
    window_seconds: float
    triggered_at: datetime
    # Which device's reading should corroborate this one (e.g. the nearest fixed
    # sensor to a mobile robot's location at alert time). In slice 1 this is supplied
    # by the alert source rather than computed by a location/proximity service — see
    # docs/ROADMAP.md. None means "no corroborating device is known," which the agent
    # must treat as insufficient evidence, not silently skip.
    corroborating_device_id: str | None = None


class IncidentState(StrEnum):
    """Explicit state machine — see services/agent_copilot/state_machine.py for the
    transition table and services/agent_copilot/state_machine.py tests for the
    invalid-transition-rejection coverage this enum requires.
    """

    RECEIVED = "received"
    TRIAGING = "triaging"
    COLLECTING_EVIDENCE = "collecting_evidence"
    ANALYZING = "analyzing"
    REQUESTING_MORE_EVIDENCE = "requesting_more_evidence"
    PROPOSING_ACTION = "proposing_action"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING_APPROVED_ACTION = "executing_approved_action"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    # PARTIAL and CANCELLED (human-approval-timeout) are planned — see ADR 0002.


class EvidenceKind(StrEnum):
    TELEMETRY = "telemetry"
    ANOMALY_SCORE = "anomaly_score"
    SOP_CITATION = "sop_citation"
    HISTORICAL_INCIDENT = "historical_incident"


class Evidence(BaseModel):
    """One piece of evidence gathered during an investigation, with the provenance
    every evidence item in the suite is required to carry.
    """

    id: str = Field(default_factory=_new_id)
    kind: EvidenceKind
    source_id: str  # device_id, document_id, or incident_id depending on kind
    summary: str
    data: dict = Field(default_factory=dict)
    confidence: float
    retrieval_score: float | None = None
    page_number: int | None = None
    producing_component: str
    timestamp: datetime = Field(default_factory=_utcnow)


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class IncidentClassification(StrEnum):
    LIKELY_REAL_EVENT = "likely_real_event"
    LIKELY_SENSOR_FAULT = "likely_sensor_fault"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class Incident(BaseModel):
    id: str = Field(default_factory=_new_id)
    alert: Alert
    state: IncidentState = IncidentState.RECEIVED
    severity: AlertSeverity | None = None
    classification: IncidentClassification | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    reasoning_summary: str | None = None  # concise, evidence-based — never raw model CoT
    trace_id: str = Field(default_factory=_new_id)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    error: str | None = None


class ProposedAction(BaseModel):
    action_type: str
    tool_name: str
    arguments: dict
    risk_level: RiskLevel
    estimated_impact: str
    alternatives: list[str] = Field(default_factory=list)


class ApprovalDecisionType(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    MODIFY_AND_APPROVE = "modify_and_approve"


class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=_new_id)
    incident_id: str
    proposed_action: ProposedAction
    reasoning_summary: str
    evidence_ids: list[str]
    risk_level: RiskLevel
    created_at: datetime = Field(default_factory=_utcnow)
    decided: bool = False


class ApprovalDecision(BaseModel):
    id: str = Field(default_factory=_new_id)
    approval_request_id: str
    approver_role: Role
    decision: ApprovalDecisionType
    modified_arguments: dict | None = None
    reason: str | None = None
    decided_at: datetime = Field(default_factory=_utcnow)


class MaintenanceTicket(BaseModel):
    id: str = Field(default_factory=_new_id)
    incident_id: str
    device_id: str
    description: str
    created_by: str = "fieldforge-copilot"
    approved_by: str
    status: str = "open"
    created_at: datetime = Field(default_factory=_utcnow)


class ToolStatus(StrEnum):
    SUCCESS = "success"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class ToolResult(BaseModel):
    tool_name: str
    status: ToolStatus
    ok: bool
    data: dict = Field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0.0
    retries: int = 0
