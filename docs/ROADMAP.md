# Roadmap and Backlog

Legend: **P0** required before any public release · **P1** portfolio differentiation · **P2** polish.
Complexity: S/M/L.

## P0 — FieldForge Docs slice 1 (done)

| ID | Title | Files | Acceptance criteria | Complexity | Depends on |
|---|---|---|---|---|---|
| DOCS-001 | Shared contracts package | `packages/contracts/` | Pydantic models for Document/DocumentPage/Chunk/RetrievalResult/Citation/EvaluationCase/EvaluationResult; `pytest` importable | S | — |
| DOCS-002 | Text/PDF extraction | `services/ingestion/` | `.txt`/`.md` native, `.pdf` native-text via pypdf; unit tests on sample corpus | S | DOCS-001 |
| DOCS-003 | Fixed-token chunker | `services/ingestion/` | Deterministic chunk boundaries with page/offset provenance; unit tests | S | DOCS-002 |
| DOCS-004 | BM25 retrieval + embedding adapter interface | `services/retrieval/` | `BM25Index.search()` returns scored, cited `RetrievalResult`; `EmbeddingAdapter` ABC + `NullEmbeddingAdapter`; unit tests | M | DOCS-001 |
| DOCS-005 | Guardrails: input/retrieval/output rails | `services/guardrails/` | File validation, PII/secret regex, injection-pattern scan, citation validation, refusal-on-no-evidence; unit tests incl. adversarial cases | M | DOCS-001 |
| DOCS-006 | Extractive answer adapter | `apps/docs_api/` | Deterministic, cites only retrieved chunk ids, no network call; unit tests | S | DOCS-004, DOCS-005 |
| DOCS-007 | FastAPI app | `apps/docs_api/` | `/health`, `/documents` (POST/GET), `/documents/{id}`, `/query`; correlation-id middleware; structured JSON logs; OpenAPI docs generated | M | DOCS-002..006 |
| DOCS-008 | Synthetic corpus | `data/generators/`, `data/samples/` | ≥5 documents (2 manuals, 1 SOP, 1 inspection report, 1 maintenance log) generated deterministically | S | — |
| DOCS-009 | Eval dataset + scorer | `evals/` | ≥15 QA cases against corpus; scorer computes real Recall@k/MRR/citation-correctness; baseline report committed | M | DOCS-007, DOCS-008 |
| DOCS-010 | Guardrail adversarial eval | `evals/datasets/guardrails_docs_v1.jsonl` | Cases for injection, embedded-instruction, malicious filename, citation spoofing, PII; scored, results committed | S | DOCS-005 |
| DOCS-011 | Tests, CI, Docker, README | `.github/workflows/`, `Dockerfile`, `README.md` | `pytest` green, `ruff`/`mypy` clean, Docker image builds, README accurate | M | all above |

## P1 — Docs milestone 2 (planned, not started)

- OCR fallback (Tesseract) for scanned pages + OCR-degradation simulator
- Qdrant dense retrieval, hybrid fusion (RRF), cross-encoder reranking
- Chunking-strategy benchmark (fixed/recursive/sentence-aware/semantic/layout-aware/parent-child/table-aware/small-to-big) with comparative report
- Bilingual English/Arabic manual + cross-lingual retrieval eval subset
- Next.js web UI: document library, query workspace, citation viewer with bounding boxes, retrieval-debug drawer
- Live LLM adapter (OpenAI-compatible + Ollama) behind the existing `ModelAdapter` interface
- RBAC (Viewer/Operator/Engineer/Safety Manager/Administrator) enforced server-side
- OpenTelemetry tracing, MLflow experiment tracking

## P0 — FieldForge Copilot slice 1 (done)

| ID | Title | Files | Acceptance criteria | Complexity | Depends on |
|---|---|---|---|---|---|
| COP-001 | Copilot contracts | `packages/contracts/copilot_models.py` | Device/TelemetryPoint/Alert/Incident/Evidence/ApprovalRequest/ApprovalDecision/MaintenanceTicket/ToolResult; 12-state `IncidentState` enum | S | — |
| COP-002 | Explicit state machine | `services/agent_copilot/state_machine.py` | Transition table; invalid transitions raise; unit-tested | S | COP-001 |
| COP-003 | Synthetic telemetry + Isolation Forest | `data/generators/generate_telemetry.py`, `services/anomaly/` | 3 devices, 4 alert scenarios, deterministic seed; real scikit-learn `IsolationForest` per device | M | — |
| COP-004 | Agent tools + orchestrator | `services/agent_copilot/tools.py`, `orchestrator.py` | 6 read-only tools + draft; `retrieve_sop` is a real HTTP call to the Docs API with graceful degradation; SOP-014 corroboration policy implemented | M | COP-001..003 |
| COP-005 | FastAPI app with approval gate | `apps/copilot_api/` | `/alerts`, `/incidents`, `/approvals`, `/approvals/{id}/decision` (role-checked server-side), `/tickets` | M | COP-004 |
| COP-006 | Tests + eval scenarios | `tests/`, `evals/datasets/copilot_scenarios_v1.jsonl` | State-machine invalid-transition tests; 12 scenarios (classification ×4, approve/reject/modify, RBAC ×2, idempotency, tool-failure, degraded-evidence); baseline committed | M | COP-005 |

All six shipped; see [evals/reports](../evals/reports) for the measured baseline
(`goal_completion_rate=1.0`, `unauthorized_action_prevention_rate=1.0` on the current 12-scenario set).

## P1 — Copilot milestone 2 (planned, not started)

- Remaining 11 of 17 program-brief tools: `check_camera_service`, `check_ocr_service`,
  `check_network_health`, `search_previous_incidents`, `retrieve_manual` (separate from
  `retrieve_sop`), `draft_operator_notification`, `send_operator_notification`,
  `request_service_restart`, `generate_incident_report`, `calculate_rate_of_change` and
  `detect_missing_data` as standalone tools (currently folded into `summarize_telemetry_window`)
- Scale evaluation scenarios from 12 to the program brief's ≥50
- `PARTIAL` and `CANCELLED` (human-approval-timeout) states — see ADR 0002
- Automatic retry/escalation policy for `REQUESTING_MORE_EVIDENCE` (currently terminal)
- Real-time telemetry chart, incident replay, agent-state visualization (needs a web UI first)
- English/Arabic incident summaries
- LangGraph adoption once Mesh needs multi-agent graph composition (ADR 0002 decision 1)

## P0 — FieldForge Mesh slice 1 (done)

| ID | Title | Files | Acceptance criteria | Complexity | Depends on |
|---|---|---|---|---|---|
| MESH-001 | A2A/MCP contracts | `packages/contracts/mesh_models.py` | AgentCard/A2ATask/A2ATaskStatus/AnalystFinding/DelegationRecord/MeshIncidentReport | S | — |
| MESH-002 | Shared telemetry service extraction | `services/telemetry/` | `TelemetryStore` moved out of Copilot's package so Mesh doesn't depend on Copilot internals; Copilot re-tested green after the move | S | — |
| MESH-003 | `telemetry-mcp` real MCP server | `services/mcp_telemetry/` | Official `mcp` SDK; 4 tools (query_telemetry, compare_devices, run_anomaly_detection, get_sensor_metadata); tool listing + tool call tested via the real SDK | M | MESH-001, MESH-002 |
| MESH-004 | Telemetry Analyst agent | `apps/mesh_telemetry_agent/` | Separately deployable; agent-card endpoint; A2A task create/get/cancel; shared-secret auth; shares tool implementations with MESH-003 | M | MESH-003 |
| MESH-005 | Incident Commander agent | `apps/mesh_commander/` | Separately deployable; real HTTP agent discovery; A2A delegation; in-process Safety Officer (always requires human approval); disagreement-preserving report | M | MESH-004 |
| MESH-006 | Tests + eval scenarios | `tests/`, `evals/datasets/mesh_scenarios_v1.jsonl` | 37 new tests incl. a real second-process integration test (uvicorn in a background thread, not mocked HTTP); 11 scenarios (delegation ×4, degradation ×4, discovery ×3); baseline committed | M | MESH-005 |

All six shipped; see [evals/reports](../evals/reports) for the measured baseline
(`goal_completion_rate=1.0`, `delegation_accuracy=1.0`, `graceful_degradation_rate=1.0`,
`agent_discovery_success_rate=1.0` on the current 11-scenario set).

## P1 — Mesh milestone 2 (planned, not started)

- Remaining agent roles: Document Intelligence, Vision Inspection, Maintenance Planner, Safety
  Officer as its own service, Report Agent
- Remaining MCP servers: `documents-mcp`, `robot-health-mcp`, `maintenance-mcp`, `deployment-mcp`
- True cross-*agent* disagreement (today's disagreement is between two signals from one analyst —
  ADR 0003 decision 5) once a second opinionated agent (e.g. Vision Inspection) exists
- Async task execution + real polling (tasks complete synchronously today — ADR 0003 decision 6)
- Scale evaluation scenarios from 11 to the program brief's ~40
- Live delegation graph UI, agent-capability registry UI, permissions explorer
- Scoped per-capability agent tokens (today's shared secret is all-or-nothing)
- Reconcile the hand-rolled A2A shape against the official `a2a-sdk`/spec — ADR 0003 decision 2

## P0 — FieldForge Ops slice 1 (done)

| ID | Title | Files | Acceptance criteria | Complexity | Depends on |
|---|---|---|---|---|---|
| OPS-001 | Ops contracts | `packages/contracts/ops_models.py` | EvaluationRun/QualityGateResult/MetricComparison/TraceSpan/Release/RollbackEvent | S | — |
| OPS-002 | Trace export | `packages/observability/tracing.py` | Fire-and-forget `export_span()`; wired into docs_api/copilot_api/mesh_telemetry_agent/mesh_commander middleware; never blocks or raises when Ops is down | S | OPS-001 |
| OPS-003 | Evaluation registry + quality gate | `apps/ops_api/gate.py`, `store.py` | Pure, unit-tested comparison logic; direction-aware (rate metrics higher-is-better, latency lower-is-better) | M | OPS-001 |
| OPS-004 | FastAPI app | `apps/ops_api/main.py` | `/evaluations`, `/quality-gate/run`, `/traces`, `/deployments` (gate-enforced), `/deployments/{id}/rollback` | M | OPS-003 |
| OPS-005 | Real ingestion + regression demo | `scripts/ingest_eval_reports.py`, `tests/integration/test_ops_regression_demo.py` | Ingests the real committed reports from all 3 products; the brief's "primary portfolio feature" CI/CD sequence runs as a real test seeded from the real Docs baseline | M | OPS-004 |
| OPS-006 | Tests | `tests/unit/test_gate.py`, `test_tracing.py`, `tests/integration/test_ops_api.py` | 29 new tests; includes a regression test for a real bug found during slice-1 testing (latency direction) | M | OPS-005 |

All six shipped. A real bug was found and fixed while building this slice: the
quality gate's first version applied "higher is better" to latency metrics too, so
a faster (better) run was reported as a failing regression — see
[ADR 0004](adr/0004-ops-quality-gate.md) decision 1.

## P1 — Ops milestone 2 (planned, not started)

- Prompt registry/versioning — no live LLM adapter exists yet to version prompts for
- Real partial-canary traffic shifting (`Release.canary_percent` is a field today, unused)
- MLflow / OpenTelemetry integration (today's trace export is a minimal bespoke span record)
- Drift monitoring (needs production traffic volume this slice doesn't have)
- Trace-explorer / evaluation-comparison web UI
- Signed evaluation reports (today's ingestion trusts the caller's JSON body)

## P0 — FieldForge Edge slice 1 (done)

| ID | Title | Files | Acceptance criteria | Complexity | Depends on |
|---|---|---|---|---|---|
| EDGE-001 | Real local dense embeddings | `services/retrieval/fieldforge_retrieval/ollama_embedding.py` | Implements the `EmbeddingAdapter` interface ADR 0001 deferred; real Ollama HTTP calls, `.available` health-checks the model is actually pulled | S | — |
| EDGE-002 | Embedded local Qdrant | `services/retrieval/fieldforge_retrieval/dense.py` | No server/Docker — `QdrantClient(path=...)`; wired into the existing `reciprocal_rank_fusion` for real hybrid retrieval | M | EDGE-001 |
| EDGE-003 | Local generative answers + citation guardrail | `packages/model_adapters/fieldforge_model_adapters/ollama_adapter.py` | Strict-JSON prompting; every citation's chunk_id and quote verified against real retrieved evidence; falls back to `ExtractiveAnswerAdapter` on any failure — observed live catching a real hallucination during development | M | — |
| EDGE-004 | Config-driven Edge mode in docs_api | `apps/docs_api/config.py`, `main.py` | `FIELDFORGE_RETRIEVAL_MODE`/`FIELDFORGE_ANSWER_MODE`, both default to unchanged slice-1 behavior; zero regression in existing tests | S | EDGE-002, EDGE-003 |
| EDGE-005 | Resource monitoring + backup/restore | `apps/docs_api/edge.py`, `store.py` | Real `psutil` + Ollama `/api/ps` snapshot; SQLite online-backup API; restore path confined to the configured backup directory (found and fixed a path-traversal gap during testing) | M | — |
| EDGE-006 | Tests + comparison benchmark | `tests/unit/test_ollama_adapters.py`, `tests/integration/test_docs_api_edge_mode.py`, `scripts/run_edge_comparison_eval.py` | 17 new tests, all skip (not fail) when Ollama isn't reachable; real measured sparse+extractive vs. hybrid+generative comparison plus a small-vs-larger local model fallback-rate comparison | M | EDGE-004, EDGE-005 |

All six shipped. Two real bugs found and fixed while building this slice: an
`OllamaEmbeddingAdapter`/`OllamaGenerativeAdapter` host-configuration override that
silently had no effect due to a module-level constant frozen at import time, and an
unrestricted `/edge/restore` path that could read any file the process could access
— see [ADR 0005](adr/0005-edge-offline-profile.md). Measured comparison results:
`evals/reports/edge_comparison_v1_report.json`.

## P1 — Edge milestone 2 (planned, not started)

- Encrypted local document storage, local audit log — see ADR 0005 decision 6 for why
  deferred rather than half-built
- GPU and Jetson hardware-profile benchmarks (this environment has neither)
- Offline English-Arabic retrieval (needs the Arabic corpus from Docs M2 first)
- Network-disconnection / cloud-sync-conflict simulation (no real cloud deployment
  exists yet to conflict with)
- Real Docker-based Qdrant server as an alternative to embedded mode

## P2 — Polish (planned)

- Demo GIF, video scripts, portfolio page copy (only after P0/P1 numbers are real)

## Non-negotiables carried on every item

No fabricated metrics. No disabled tests to pass CI. No secrets committed. Every P0 item ships
with its own tests before being marked done.
