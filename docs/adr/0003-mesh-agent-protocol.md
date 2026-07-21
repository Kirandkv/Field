# ADR 0003: Mesh protocol choices — hand-rolled A2A shape, real MCP SDK, 2-agent slice

- Status: Accepted
- Date: 2026-07-21

## Context

FieldForge Mesh (milestone M4) needs at least two independently deployable agents
communicating over A2A, at least one original MCP server, and the permission/conflict
handling the program brief specifies across seven possible agent roles (Incident
Commander, Telemetry Analyst, Document Intelligence, Vision Inspection, Maintenance
Planner, Safety Officer, Report Agent). Building all seven for a first slice repeats
the exact mistake ADR 0001 and ADR 0002 were written to avoid.

## Decisions

1. **Two agents only, this slice**: Incident Commander (`apps/mesh_commander`) and
   Telemetry Analyst (`apps/mesh_telemetry_agent`), each a separately runnable FastAPI
   process with its own port, own process, own failure domain. The other five roles
   are designed (see [MESH_OVERVIEW.md](../architecture/MESH_OVERVIEW.md)) but not
   built — see [docs/ROADMAP.md](../ROADMAP.md).

2. **A2A is a hand-rolled, A2A-shaped REST API, not the `a2a-sdk` package.** The A2A
   protocol's vocabulary (AgentCard, Task, Message, Artifact) is followed —
   `GET /.well-known/agent-card`, `POST /tasks`, `GET /tasks/{id}`,
   `POST /tasks/{id}/cancel` — but implemented directly with FastAPI/Pydantic rather
   than a third-party SDK. Reasoning: the SDK's exact current API surface can't be
   verified against live documentation from this environment, and a dependency this
   central to the product's own claim ("real A2A") is worth owning outright, the same
   tradeoff ADR 0001 made for BM25-over-a-vector-SDK. This is disclosed, not
   presented as the official protocol — see
   [docs/INSPIRATION_AND_ATTRIBUTION.md](../INSPIRATION_AND_ATTRIBUTION.md).

3. **`telemetry-mcp` uses the real, official `mcp` Python SDK** (PyPI `mcp`, Anthropic's
   MCP SDK), not a hand-rolled approximation — unlike decision 2, MCP's SDK is the
   thing being demonstrated, so using anything else would defeat the point. It exposes
   `query_telemetry`, `compare_devices`, `run_anomaly_detection`, `get_sensor_metadata`
   — the exact four tools the program brief specifies for `telemetry-mcp` — backed by
   the same `TelemetryStore`/`DeviceAnomalyDetector` FieldForge Copilot already uses
   (`services/agent_copilot`, `services/anomaly`), so Mesh doesn't fork that logic.

4. **Safety Officer is in-process logic inside Incident Commander, not a third
   service, this slice.** The brief's requirement is "at least two agents... separately
   deployable" — met by Commander + Telemetry Analyst. Splitting Safety Officer out
   is planned (M2) once there's a second decision-maker (e.g. Maintenance Planner)
   for it to actually adjudicate between; a policy function with only one caller
   gains nothing from being its own service yet.

5. **Conflict preservation is demonstrated within Telemetry Analyst's own response**,
   not across two independent agents: it returns both a rule-based corroboration
   classification (SOP-014 policy: compare the alerting device against its
   corroborating device) and a model-based anomaly classification (Isolation Forest
   on the alerting device's own history) as two independent, sometimes-disagreeing
   signals. Incident Commander's final report keeps both, explicitly, rather than
   collapsing them into one number. This is a real, scoped-down instance of "preserve
   disagreement instead of silently forcing consensus" — true cross-*agent*
   disagreement (e.g. Telemetry vs. a future Vision Inspection Agent) needs a second
   opinionated agent to exist first, tracked for M2.

6. **Task execution is synchronous within the HTTP call that creates it.** A task
   reaches a terminal state (`completed`/`failed`) before `POST /tasks` returns. The
   full task-lifecycle API (`GET /tasks/{id}`, `POST /tasks/{id}/cancel`) is still
   implemented and tested — cancelling an already-terminal task returns its actual
   terminal status rather than erroring — so the shape is correct for M2, when
   long-running tasks (e.g. involving a slower agent) will need real async polling.

7. **Service-to-service auth is a static shared-secret header**
   (`X-FieldForge-Agent-Token`), checked by Telemetry Analyst on every `POST /tasks`,
   not OAuth/mTLS. Same dev-friendly-auth posture as Copilot's role header (ADR 0002
   decision 4) — real enforcement, minimal ceremony. Full agent-to-agent auth
   (scoped tokens per capability) is planned for M2 alongside the rest of the suite's
   RBAC work.

## Consequences

- Positive: Incident Commander genuinely cannot see or touch Telemetry Analyst's
  internals — every interaction crosses a real process/network boundary, so failure
  injection (agent down, malformed task, timeout) exercises real code paths, not
  mocked ones.
- Positive: `telemetry-mcp` can be pointed at by any real MCP client (Claude Desktop,
  an MCP inspector) for a live demo, not just this suite's own agents.
- Negative: no cross-agent disagreement demo yet (decision 5) — flagged, not hidden.
- Negative: A2A implementation will need reconciling against the official SDK/spec
  before any claim of interoperability with a third-party A2A agent — tracked M2.
