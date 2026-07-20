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

| # | Milestone | Depends on |
|---|---|---|
| M1 | Docs vertical slice 1 (this doc, §4) | — |
| M2 | Docs: OCR + multimodal + Qdrant hybrid retrieval + web UI | M1 |
| M3 | Copilot vertical slice (single agent, human approval, one flagship scenario) | M1 |
| M4 | Mesh vertical slice (2+ agents, one MCP server, one A2A task) | M3 |
| M5 | Ops vertical slice (trace explorer + one quality gate demo) | M3 |
| M6 | Edge profile | M2 |

See [ROADMAP.md](ROADMAP.md) for the issue-level backlog.
