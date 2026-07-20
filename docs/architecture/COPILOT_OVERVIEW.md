# Architecture — FieldForge Copilot (Slice 1)

Status: describes what is implemented today. See [ADR 0002](../adr/0002-copilot-agent-architecture.md)
for the reasoning behind each major decision below.

## Component diagram (Implemented)

```mermaid
flowchart LR
    C[Client] -->|POST /alerts or /demo/scenarios/x/trigger| API["apps/copilot_api"]
    API --> ORC["orchestrator.investigate()"]

    subgraph Tools["services/agent_copilot tools"]
        T1[get_device]
        T2[get_sensor_history]
        T3[summarize_telemetry_window]
        T4[run_isolation_forest]
        T5[retrieve_sop]
        T6[draft_maintenance_ticket]
    end

    ORC --> T1 & T2 & T3 --> TS[(TelemetryStore\ndata/samples/telemetry)]
    ORC --> T4 --> AF["DeviceAnomalyDetector\n(scikit-learn IsolationForest, fit at startup)"]
    ORC -->|HTTP POST /query| T5 -->|"real service call"| DOCS["FieldForge Docs API\n(separate process)"]
    ORC --> T6 --> PA[ProposedAction]

    ORC --> SM["AgentStateMachine\n(explicit transition table)"]
    SM --> INC[(Incident — SQLite)]
    PA --> AR[(ApprovalRequest — SQLite)]

    H[Safety Manager] -->|"POST /approvals/id/decision\nX-FieldForge-Role: safety_manager"| API
    API -->|approve/modify| MT[(MaintenanceTicket — SQLite)]
```

## Sequence — flagship scenario end to end

```mermaid
sequenceDiagram
    participant C as Client
    participant API as copilot_api
    participant O as orchestrator
    participant D as Docs API (separate service)
    participant SM as Safety Manager

    C->>API: POST /demo/scenarios/alert-2026-06-14/trigger
    API->>O: investigate(alert)
    O->>O: RECEIVED -> TRIAGING (severity=HIGH)
    O->>O: TRIAGING -> COLLECTING_EVIDENCE
    O->>O: get_device, get_sensor_history (FF-R07 + FIX-B3-02)
    O->>O: run_isolation_forest(FF-R07, 1180ppm) -> is_anomaly=True
    O->>D: HTTP POST /query "methane survey alert response..."
    alt Docs API reachable
        D-->>O: cited SOP-014 + manual excerpts
    else Docs API unreachable
        O->>O: continue with degraded evidence (no crash)
    end
    O->>O: ANALYZING: corroborator normal -> likely_sensor_fault
    O->>O: PROPOSING_ACTION -> draft_maintenance_ticket
    O->>O: AWAITING_APPROVAL
    O-->>API: Incident + ApprovalRequest
    API-->>C: 201 {state: awaiting_approval, ...}

    SM->>API: POST /approvals/{id}/decision {decision: approve}\nX-FieldForge-Role: safety_manager
    API->>API: role check (403 if not safety_manager)
    API->>API: EXECUTING_APPROVED_ACTION -> create MaintenanceTicket
    API->>API: VERIFYING -> COMPLETED
    API-->>SM: 200 {state: completed}
```

## State machine (Implemented — 12 states)

```mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> TRIAGING
    TRIAGING --> COLLECTING_EVIDENCE
    TRIAGING --> FAILED
    COLLECTING_EVIDENCE --> ANALYZING
    COLLECTING_EVIDENCE --> FAILED
    ANALYZING --> REQUESTING_MORE_EVIDENCE
    ANALYZING --> PROPOSING_ACTION
    ANALYZING --> FAILED
    PROPOSING_ACTION --> AWAITING_APPROVAL
    PROPOSING_ACTION --> FAILED
    AWAITING_APPROVAL --> EXECUTING_APPROVED_ACTION: approve / modify_and_approve
    AWAITING_APPROVAL --> REJECTED: reject
    EXECUTING_APPROVED_ACTION --> VERIFYING
    EXECUTING_APPROVED_ACTION --> FAILED
    VERIFYING --> COMPLETED
    VERIFYING --> FAILED
    REQUESTING_MORE_EVIDENCE --> [*]
    COMPLETED --> [*]
    REJECTED --> [*]
    FAILED --> [*]
```

Every arrow above is a literal entry in `services/agent_copilot/fieldforge_agent_copilot/state_machine.py`'s
transition table. Any transition not drawn here raises `InvalidTransitionError` — see
`tests/unit/test_state_machine.py`.

## Trust boundary: cross-service call to Docs

`retrieve_sop` is the one point where Copilot calls another FieldForge service over
the network rather than a local function. It is treated as untrusted-until-checked:
a non-200 response, a connection failure, or a `refused: true` body are all handled
explicitly (`ToolStatus.UNAVAILABLE` / `ERROR`), and the orchestrator never blocks
on it — see [ADR 0002](../adr/0002-copilot-agent-architecture.md) decision 2 and
`tests/unit/test_orchestrator.py::test_investigation_completes_without_crashing_when_docs_api_unavailable`.

## What's not implemented (planned)

- 11 of the 17 tools listed in the program brief (`check_camera_service`,
  `search_previous_incidents`, `send_operator_notification`, `request_service_restart`,
  `generate_incident_report`, etc.) — see [docs/ROADMAP.md](../ROADMAP.md).
- Voice briefing, English/Arabic summaries, incident replay UI, confidence-calibration
  view — all listed as "unique portfolio customizations" in the program brief, all
  deferred until the core agent loop above has a UI to sit behind.
- LangGraph / graph-framework orchestration — deferred to the Mesh milestone.
- Full RBAC — only the approval endpoint enforces a role today.
