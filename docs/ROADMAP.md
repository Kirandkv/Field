# Roadmap and Backlog

Legend: **P0** required before any public release · **P1** portfolio differentiation · **P2** polish.
Complexity: S/M/L.

## P0 — FieldForge Docs slice 1 (this milestone)

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

## P1 — Copilot vertical slice (planned, not started)

- Single agent, explicit state machine, read-only tools first (telemetry, SOP retrieval)
- Human-approval gate for state-changing tools (draft/create maintenance ticket)
- ≥50 evaluation scenarios per program brief
- Flagship demo: methane-spike-vs-sensor-fault scenario

## P1 — Mesh vertical slice (planned, not started)

- 2 agents minimum, ≥1 independently deployable, ≥1 original MCP server, ≥1 real A2A task exchange
- Agent permission matrix, conflict-preservation policy

## P1 — Ops vertical slice (planned, not started)

- Trace explorer over Docs' correlation IDs (first real trace source)
- One quality gate demo (regression → PR gate fails → fix → gate passes) per program brief §Profile D

## P2 — Polish (planned)

- FieldForge Edge offline profile
- Demo GIF, video scripts, portfolio page copy (only after P0/P1 numbers are real)

## Non-negotiables carried on every item

No fabricated metrics. No disabled tests to pass CI. No secrets committed. Every P0 item ships
with its own tests before being marked done.
