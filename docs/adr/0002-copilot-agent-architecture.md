# ADR 0002: Copilot agent architecture — hand-rolled FSM, cross-service SOP retrieval, sandboxed writes

- Status: Accepted
- Date: 2026-07-20

## Context

FieldForge Copilot (milestone M3) is a single human-supervised agent that investigates
incident alerts, gathers evidence, and proposes actions that require Safety Manager
approval before anything state-changing happens. It needs to reuse FieldForge Docs
(already built, [ADR 0001](0001-monorepo-vertical-slice.md)) for SOP retrieval, and needs
a real anomaly-detection component given the candidate's stated Isolation Forest experience.

## Decisions

1. **Explicit state machine is hand-rolled Python, not LangGraph.** The program's default
   stack calls for "LangGraph or a similarly explicit state-graph framework." A small
   `AgentStateMachine` class with an explicit transition table (`services/agent_copilot/state_machine.py`)
   is that "similarly explicit" framework: every transition is a table lookup, invalid
   transitions raise and are unit-tested, and there is no hidden control flow. Adopting
   LangGraph is deferred to the Mesh milestone (M4), where multi-agent graph composition
   actually needs it — pulling in a framework dependency before there's a second agent to
   coordinate would be premature.

2. **`retrieve_sop` calls the FieldForge Docs API over HTTP, not an in-process import.**
   Copilot and Docs are separate deployable services in the target architecture (per the
   program's A2A/service-oriented direction). Calling Docs' already-running `/query`
   endpoint (`FIELDFORGE_DOCS_API_URL`, default `http://localhost:8000`) — instead of
   re-importing `fieldforge_retrieval`/`fieldforge_ingestion` and rebuilding a second BM25
   index in-process — is the honest service boundary, and it forces Copilot to handle a
   real failure mode: if Docs is unreachable, `retrieve_sop` returns a `ToolResult` with
   `status="unavailable"`, and the agent's state machine treats missing SOP evidence as
   grounds to transition to `REQUESTING_MORE_EVIDENCE` rather than guessing or crashing.
   This is the same graceful-degradation posture as Docs' `NullEmbeddingAdapter` (ADR 0001).

3. **State-changing tools write to Copilot's own SQLite store only — no real external
   ticketing/notification system exists to call.** `create_maintenance_ticket` is the
   "sandboxed simulated write action" the guardrail architecture requires: it is real
   code with a real effect (a row appears, retrievable via the API), but it never reaches
   an external system, because FieldForge Industries' fictional maintenance system isn't
   part of this suite. `send_operator_notification` and `request_service_restart` are
   listed as required tools in the program brief but are **not implemented in slice 1**
   — they are the two tools in the brief's list with no plausible sandboxed target, and
   adding them as no-ops would be exactly the "half-finished implementation" this program
   forbids. Tracked in [docs/ROADMAP.md](../ROADMAP.md) as planned once there's a target
   (e.g. a fake webhook receiver) to simulate against.

4. **RBAC is scoped to the one action that matters for this slice**: approving a proposed
   action requires an `X-FieldForge-Role: safety_manager` header, checked server-side
   (`apps/copilot_api`), returning 403 otherwise. This is not the full five-role matrix
   from the program brief — it is the minimum enforcement needed to make "human approval
   required" a real, testable constraint rather than a UI suggestion. Full RBAC across
   every endpoint is a shared cross-product concern deferred to the same M2 milestone as
   Docs' RBAC (ADR 0001), so it's built once, not twice.

5. **Isolation Forest is fit in-memory per device at service startup**, from the synthetic
   telemetry history in `data/samples/telemetry/`, using scikit-learn directly. No model
   registry, no persisted artifact, no MLflow run — that tooling belongs to the Ops
   milestone (M5), which is explicitly the product responsible for model/prompt
   versioning across the suite. Slice 1 just needs the anomaly score to be real, not a
   hardcoded number.

## Consequences

- Positive: Copilot exercising Docs' live API is a real integration test of the suite's
  "connected portfolio" claim, not just a shared-schema claim.
- Positive: every state-changing action in this slice is genuinely reversible/inspectable
  (a SQLite row), so there is no risk of the agent taking an irreversible action during
  development or evaluation.
- Negative: running the Copilot flagship scenario end-to-end requires the Docs API to
  also be running (or the scenario predictably degrades to `REQUESTING_MORE_EVIDENCE`,
  which is itself demonstrated as a passing eval case, not treated as a bug).
- Negative: two of the program brief's seventeen listed Copilot tools are not implemented
  this slice (see decision 3). Documented, not hidden.
