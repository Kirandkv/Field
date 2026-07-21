# Architecture — FieldForge Mesh (Slice 1)

Status: describes what is implemented today. See
[ADR 0003](../adr/0003-mesh-agent-protocol.md) for the reasoning behind each choice.

## Component diagram (Implemented)

```mermaid
flowchart LR
    subgraph Commander["apps/mesh_commander — Incident Commander"]
        REG[Agent Registry]
        SO["Safety Officer\n(in-process policy)"]
        MSTORE[(MeshIncidentReport — SQLite)]
    end

    subgraph Analyst["apps/mesh_telemetry_agent — Telemetry Analyst"]
        CARD["/.well-known/agent-card"]
        TASKS["/tasks (A2A-shaped)"]
        TSTORE[(In-memory task store)]
    end

    subgraph MCP["services/mcp_telemetry — telemetry-mcp"]
        MT[query_telemetry]
        MC[compare_devices]
        MA[run_anomaly_detection]
        MM[get_sensor_metadata]
    end

    CORE["fieldforge_mcp_telemetry.core\n(shared tool implementations)"]

    Client -->|"POST /agents/discover {endpoint}"| REG
    REG -->|"GET /.well-known/agent-card"| CARD
    Client -->|"POST /incidents"| Commander
    Commander -->|"POST /tasks (A2A)\nX-FieldForge-Agent-Token"| TASKS
    TASKS --> CORE
    MT & MC & MA & MM --> CORE
    CORE --> TELSTORE[(TelemetryStore\nservices/telemetry)]
    CORE --> AF["DeviceAnomalyDetector\nservices/anomaly"]
    TASKS --> Commander
    Commander --> SO --> MSTORE

    MCPClient["Any real MCP client\n(Claude Desktop, inspector)"] -->|streamable-http| MCP
```

`fieldforge_mcp_telemetry.core` is called by both the MCP server (`server.py`) and the
Telemetry Analyst's A2A HTTP handler — one implementation, two transports (ADR 0003
decision 3). `services/telemetry` and `services/anomaly` are shared with FieldForge
Copilot (extracted there once Mesh needed them too).

## Sequence — flagship scenario, real cross-process delegation

```mermaid
sequenceDiagram
    participant C as Client
    participant Cmd as Incident Commander
    participant TA as Telemetry Analyst (separate process)

    C->>Cmd: POST /agents/discover {endpoint: TA_url}
    Cmd->>TA: GET /.well-known/agent-card
    TA-->>Cmd: AgentCard (id, role, capabilities, supported_task_types)
    Cmd->>Cmd: register (endpoint = the address actually reached, not TA's self-report)

    C->>Cmd: POST /incidents {device_id, value, triggered_at, window_seconds, corroborating_device_id}
    Cmd->>Cmd: find_by_role("telemetry-analyst")
    Cmd->>TA: POST /tasks {task_type: investigate_telemetry, input}\nX-FieldForge-Agent-Token
    TA->>TA: compare_devices() + run_anomaly_detection()
    TA-->>Cmd: A2ATask {status: completed, artifacts: [AnalystFinding], messages: [requester, agent]}
    Cmd->>Cmd: Safety Officer decides (always requires_human_approval=true)
    Cmd-->>C: MeshIncidentReport {safety_decision, disagreement_flag, delegation_log}
```

## Trust boundary: Commander never executes

```mermaid
flowchart LR
    Cmd[Incident Commander] -->|delegate| TA[Telemetry Analyst]
    Cmd -->|"block or escalate\n(never execute)"| Human[Human / FieldForge Copilot]
    TA -->|read-only tools only| Data[(Telemetry data)]
```

Telemetry Analyst's tools are all read-only. Incident Commander has no write
capability at all in this slice — every `MeshIncidentReport.requires_human_approval`
is `true` (see `apps/mesh_commander/fieldforge_mesh_commander/safety_officer.py`).
Executing an approved action is FieldForge Copilot's job, not Mesh's — the two
products intentionally don't duplicate that responsibility.

## Permission matrix (slice 1)

| Agent | Can read telemetry | Can delegate | Can execute actions | Can approve |
|---|---|---|---|---|
| Telemetry Analyst | Yes (own data only) | No | No | No |
| Incident Commander | Via delegation only | Yes | **No — never** | No |
| Human / Safety Manager | Via reports | — | Via FieldForge Copilot | Yes |

## What's not implemented (planned)

- Document Intelligence, Vision Inspection, Maintenance Planner, Safety Officer (as
  its own service), Report Agent — see [docs/ROADMAP.md](../ROADMAP.md).
- `documents-mcp`, `robot-health-mcp`, `maintenance-mcp`, `deployment-mcp`.
- True cross-*agent* disagreement (this slice demonstrates disagreement between two
  signals from one analyst — see ADR 0003 decision 5).
- Async task execution / real task polling (tasks complete synchronously today —
  ADR 0003 decision 6).
- OAuth/mTLS agent-to-agent auth (static shared-secret token today).
