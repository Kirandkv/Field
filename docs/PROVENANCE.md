# Provenance Map

Greenfield repository — every file below was authored in this session for this project. No file
was copied from an external repository, template, or prior codebase. This map exists per the
program's audit process so future contributors/reviewers have a starting reference point instead
of an empty file.

| Component | Origin | License | Modification | Attribution required | Notes |
|---|---|---|---|---|---|
| `packages/contracts/*` | Original | Repo license | — | No | Pydantic schemas written for this project |
| `services/ingestion/*` | Original | Repo license | — | No | Uses `pypdf` (Apache-2.0/BSD) via its public API |
| `services/retrieval/*` | Original | Repo license | — | No | Uses `rank_bm25` (Apache-2.0) via its public API; BM25/RRF are published algorithms, not copied code |
| `services/guardrails/*` | Original | Repo license | — | No | Regex patterns hand-written for this project's threat model |
| `apps/docs_api/*`, `apps/copilot_api/*`, `apps/mesh_commander/*`, `apps/mesh_telemetry_agent/*`, `apps/ops_api/*` | Original | Repo license | — | No | Uses `fastapi`/`uvicorn` via their public API |
| `services/agent_copilot/*` | Original | Repo license | — | No | State machine, tools, orchestrator written for this project |
| `services/telemetry/*` | Original | Repo license | — | No | Shared by Copilot and Mesh — extracted from Copilot once Mesh needed it too |
| `services/anomaly/*` | Original | Repo license | — | No | Uses `scikit-learn`'s `IsolationForest` (BSD-3-Clause) via its public API |
| `services/mcp_telemetry/*` | Original | Repo license | — | No | Uses the official `mcp` SDK (MIT) via its public API — see ADR 0003 decision 3 |
| `services/retrieval/fieldforge_retrieval/ollama_embedding.py`, `dense.py` | Original | Repo license | — | No | Calls Ollama's HTTP API and uses `qdrant-client` (Apache-2.0) via its public API — no Ollama or Qdrant source vendored |
| `packages/model_adapters/fieldforge_model_adapters/ollama_adapter.py` | Original | Repo license | — | No | Calls Ollama's HTTP API; prompt template and citation-validation guardrail written for this project |
| `apps/docs_api/fieldforge_docs_api/edge.py` | Original | Repo license | — | No | Uses `psutil` (BSD-3-Clause) via its public API |
| `data/generators/*`, `data/samples/*` | Original | Repo license | — | No | Fictional content, see [DATA_CARD.md](../DATA_CARD.md) |
| `evals/*` | Original | Repo license | — | No | Hand-authored QA/adversarial/scenario cases |

Third-party packages consumed as dependencies (not vendored): see
`docs/INSPIRATION_AND_ATTRIBUTION.md` for the license list. This table will grow as inspiration
repositories are actually supplied and reviewed, and as future milestones introduce new components.
