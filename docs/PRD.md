# FieldForge AI Suite — Product Requirements Document

Status: living document. Suite-wide. Per-product detail lives in each product's own `docs/` once that product's slice starts.

## 1. Program summary

FieldForge AI Suite is a portfolio of connected AI-engineering products built around one fictional
industrial operator, **FieldForge Industries**, which runs a fleet of mobile inspection robots and
fixed environmental sensors across gas/petrochemical-style field sites. The suite exists to
demonstrate production AI engineering practice — retrieval, agents, multi-agent orchestration,
guardrails, evaluation, and LLMOps — with measured results, not narrative claims.

Products (built incrementally, one vertical slice at a time):

1. **FieldForge Docs** — multimodal document intelligence / advanced RAG. *(this repo's current focus)*
2. **FieldForge Copilot** — single supervised agent for incident investigation. *(planned)*
3. **FieldForge Mesh** — multi-agent incident command over MCP + A2A. *(planned)*
4. **FieldForge Ops** — LLMOps control plane (eval, trace, deploy, monitor) for 1–3. *(planned)*
5. **FieldForge Edge** — offline/local deployment profile. *(optional, planned)*

## 2. Non-goals

- Not a general-purpose chatbot product.
- Not a wrapper that forwards user text to an LLM API with no retrieval/agent/eval structure around it.
- Not a claim of real deployment, real customers, or real incident data — the operator and fleet are synthetic.
- Not going to fabricate benchmark numbers. Any metric not yet measured is written as `TBD`.

## 3. Users (personas)

| Persona | Needs |
|---|---|
| Field technician | Fast, cited answers from manuals/SOPs while at equipment |
| Maintenance engineer | Cross-reference maintenance history against manuals; draft actions |
| Safety manager | Approve consequential actions; verify evidence before sign-off |
| Operations analyst | Investigate telemetry incidents; compare devices |
| Auditor | Verify provenance of every claim and action taken |

## 4. Current milestone: FieldForge Docs — vertical slice 1

**Goal:** one complete path — upload a document → ingest → chunk → index → ask a question →
get a grounded, cited answer — running end-to-end locally with one command, with real
(not fabricated) retrieval metrics from a versioned eval set.

### User story
> As a field technician, I upload FieldForge Industries manuals/SOPs, ask a question in
> plain English, and get an answer that cites the exact source page — or an explicit
> refusal if the documents don't support an answer.

### In scope for slice 1
- Ingestion: `.txt` / `.md` native, `.pdf` native-text extraction (OCR fallback marked planned).
- Chunking: fixed-token strategy (pluggable interface; only one strategy implemented now).
- Retrieval: BM25 sparse retrieval (always available, no external services). Dense embedding
  adapter interface exists but defaults to a `NullEmbeddingAdapter` — the system runs fully
  offline out of the box and degrades gracefully rather than fabricating a dense score.
- Answer generation: deterministic **extractive** answer adapter by default (concatenates and
  cites the top-supporting chunks; never invents text) — no API key required to run. Pluggable
  interface for a real LLM adapter (OpenAI-compatible / Ollama) is defined but not wired to a
  live provider in this slice (documented as planned; see [ROADMAP.md](ROADMAP.md)).
- Guardrails: input validation (file type/size), PII/secret pattern detection, prompt-injection
  pattern detection on ingested text (input + retrieval rails). Output rail: citation validation
  and refusal-on-no-evidence.
- API: FastAPI, `/health`, `/documents`, `/documents/{id}`, `/query`.
- Eval: versioned QA dataset generated against the synthetic corpus this repo ships, scored for
  Recall@k / MRR / citation correctness with an actual scorer run (numbers in
  [evals/reports](../evals/reports)).
- Tests: unit tests for chunking, retrieval fusion, guardrails; API tests via FastAPI TestClient.

### Explicitly out of scope for slice 1 (tracked separately, see backlog)
- OCR (Tesseract) fallback for scanned pages
- Vision/multimodal (tables, diagrams) question answering
- Qdrant-backed dense retrieval, reranking, RRF, query rewriting, corrective retrieval
- Web UI (Next.js) — slice 1 is API-only, exercised via tests + CLI/HTTP
- Auth/RBAC (Viewer/Operator/... roles) — slice 1 has no multi-tenant access control yet
- OpenTelemetry distributed tracing — slice 1 has structured JSON logs + correlation IDs only
- Copilot, Mesh, Ops, Edge products

## 5. Non-functional requirements

- Runs fully offline with zero external API keys (degrades to sparse retrieval + extractive answers).
- No secrets committed; `.env.example` documents required/optional config.
- Deterministic test suite (fake adapters only in tests; no network calls in CI).
- Every retrieval result and generated answer carries provenance (source doc, page, chunk id, score).

## 6. Milestones

| # | Milestone | Status | Depends on |
|---|---|---|---|
| M1 | Docs vertical slice 1 (this doc, §4) | Done | — |
| M2 | Docs: OCR + multimodal + Qdrant hybrid retrieval + web UI | Planned | M1 |
| M3 | Copilot vertical slice (single agent, human approval, one flagship scenario) | Done | M1 |
| M4 | Mesh vertical slice (2+ agents, one MCP server, one A2A task) | Done | M3 |
| M5 | Ops vertical slice (trace explorer + one quality gate demo) | Done | M3 |
| M6 | Edge profile | Planned | M2 |

See [ROADMAP.md](ROADMAP.md) for the issue-level backlog.

## 7. Milestone M3: FieldForge Copilot — vertical slice 1

**Goal:** one complete supervised-agent workflow — alert → investigate (telemetry +
anomaly score + cross-service SOP retrieval) → propose action → human approval →
execute — running end to end locally, sharing the corpus and services already built
for Docs rather than a disconnected demo dataset.

### User story
> As a safety manager, I receive a methane alert investigated by Copilot, see the
> evidence it gathered (telemetry, anomaly score, cited SOP text) and its concise
> reasoning, and approve, reject, or modify the proposed action — nothing happens to
> the fleet without my decision.

### In scope for slice 1
Explicit 12-state incident state machine; 6 read-only/preparatory tools plus a
human-gated `create_maintenance_ticket`; real scikit-learn Isolation Forest anomaly
scoring per device; `retrieve_sop` as a genuine HTTP call to the Docs API with tested
graceful degradation; server-enforced approval RBAC; 12 scenario-level eval cases.
See [docs/architecture/COPILOT_OVERVIEW.md](architecture/COPILOT_OVERVIEW.md) for the
full diagrams and [ADR 0002](adr/0002-copilot-agent-architecture.md) for the
architecture decisions.

### Explicitly out of scope for slice 1
11 of the program brief's 17 tools, `PARTIAL`/`CANCELLED` states, automatic
retry/escalation, voice/bilingual briefings, a web UI, and the ≥50-scenario eval
suite (currently 12) — see [docs/ROADMAP.md](ROADMAP.md).

## 8. Milestone M4: FieldForge Mesh — vertical slice 1

**Goal:** two independently deployable agents communicating over a real A2A-shaped
protocol, plus one original MCP server, investigating the same flagship incident
Docs and Copilot already know about — proving the suite is connected, not three
demos sharing a README.

### User story
> As an operations analyst, I ask Incident Commander to investigate an alert. It
> discovers the Telemetry Analyst agent, delegates the investigation over a real
> network call, and returns a report that preserves disagreement between its two
> independent signals rather than picking one — and, like Copilot, never takes
> action on its own.

### In scope for slice 1
Two separately-deployable FastAPI services (Incident Commander, Telemetry Analyst);
a real MCP server (`telemetry-mcp`, official SDK) exposing the same tool
implementations the A2A path uses; agent discovery over a genuine HTTP call to
`/.well-known/agent-card`; shared-secret A2A auth; a Safety Officer policy that
always requires human approval; 11 scenario-level eval cases run against two live
processes. See [docs/architecture/MESH_OVERVIEW.md](architecture/MESH_OVERVIEW.md)
and [ADR 0003](adr/0003-mesh-agent-protocol.md).

### Explicitly out of scope for slice 1
5 of the program brief's 7 agent roles, 4 of its 5 MCP servers, true cross-agent
(rather than cross-signal) disagreement, async task execution, OAuth/mTLS
agent-to-agent auth, and the ~40-scenario eval suite (currently 11) — see
[docs/ROADMAP.md](ROADMAP.md).

## 9. Milestone M5: FieldForge Ops — vertical slice 1

**Goal:** ingest the real evaluation reports Docs/Copilot/Mesh already produce,
enforce a quality gate against their committed baselines, collect trace spans from
all four products, and gate-enforce a deployment/rollback registry — proving the
"evaluate, trace, deploy, monitor" control-plane concept with real data rather than
a fabricated dashboard.

### User story
> As the maintainer, I run a product's eval suite, ingest the result into Ops, and
> get a pass/fail decision against the committed baseline. If it fails, I can see
> exactly which metric regressed and by how much, and deployment is blocked until
> it passes — enforced by the API, not by me remembering to check.

### In scope for slice 1
Evaluation registry ingesting real `evals/reports`/`evals/baselines` JSON;
direction-aware quality gate (rate metrics higher-is-better, latency
lower-is-better — the second branch exists because of a real bug found while
building this slice, see [ADR 0004](adr/0004-ops-quality-gate.md)); fire-and-forget
trace export wired into all four other products' request middleware; a
gate-enforced deployment/rollback registry. The brief's "prompt regression → gate
fails → fix → gate passes → deploy → rollback" demonstration runs as a real
integration test seeded from the actual committed Docs baseline. See
[docs/architecture/OPS_OVERVIEW.md](architecture/OPS_OVERVIEW.md).

### Explicitly out of scope for slice 1
Prompt registry/versioning (no live LLM adapter exists yet to version prompts for),
real partial-canary traffic shifting, MLflow/OpenTelemetry integration, drift
monitoring, and any UI (trace explorer, evaluation comparison) — see
[docs/ROADMAP.md](ROADMAP.md).
