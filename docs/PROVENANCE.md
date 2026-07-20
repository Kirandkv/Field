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
| `apps/docs_api/*` | Original | Repo license | — | No | Uses `fastapi`/`uvicorn` via their public API |
| `data/generators/*`, `data/samples/*` | Original | Repo license | — | No | Fictional content, see [DATA_CARD.md](../DATA_CARD.md) |
| `evals/*` | Original | Repo license | — | No | Hand-authored QA/adversarial cases |

Third-party packages consumed as dependencies (not vendored): see
`docs/INSPIRATION_AND_ATTRIBUTION.md` for the license list. This table will grow as inspiration
repositories are actually supplied and reviewed, and as later milestones (Copilot/Mesh/Ops/Edge)
introduce new components.
