# ADR 0001: Monorepo layout, vertical-slice-first delivery, BM25-first retrieval

- Status: Accepted
- Date: 2026-07-20

## Context

FieldForge AI Suite spans five connected products (Docs, Copilot, Mesh, Ops, Edge). Building all
five simultaneously risks five shallow, unfinished demos instead of one deep, evaluable product.
The working directory had no prior repository — this is a greenfield decision.

## Decision

1. **One monorepo**, `fieldforge/`, shared by all five products, using the
   `apps/ · services/ · packages/ · evals/ · docs/` layout specified in the program brief, so
   contracts and conventions are shared instead of duplicated per-repo.
2. **Build FieldForge Docs first**, and only its vertical slice 1 (ingest → chunk → BM25 retrieve →
   extractive cited answer). Copilot, Mesh, Ops, Edge are designed (PRD-level) but not implemented
   until Docs slice 1 is real and evaluable.
3. **Retrieval defaults to BM25 sparse-only**, with a dense `EmbeddingAdapter` interface defined but
   defaulting to a `NullEmbeddingAdapter`. No external vector DB or embedding API is required to run
   the vertical slice.
4. **Answer generation defaults to a deterministic extractive adapter** (no LLM API call), with a
   `ModelAdapter` interface defined for a future live provider (OpenAI-compatible / Ollama).
5. **Storage is SQLite** for slice 1, not PostgreSQL/Qdrant — those are planned for M2 once a real
   multi-user deployment scenario exists to justify them.

## Consequences

- Positive: the suite runs with `pip install` only — no Docker Compose stack required to try slice 1
  — while docker-compose.yml exists for the eventual full stack.
- Positive: retrieval and answer metrics measured in `evals/reports` are real, not simulated against
  a mocked LLM.
- Negative: BM25-only retrieval will score lower on paraphrase/cross-lingual queries than dense/hybrid
  retrieval — this is expected and documented, not hidden. The chunking/retrieval benchmark comparing
  strategies (fixed/recursive/semantic/etc.) from the program brief is deferred to M2 for the same
  reason: it requires the dense adapter to be meaningful.
- Negative: no auth/RBAC in slice 1 — acceptable because slice 1 has no multi-tenant data yet.

## Alternatives considered

- Building thin slices of all five products at once — rejected: produces five demos with no real
  evaluation depth, which is exactly the "hackathon demo" failure mode this program is meant to avoid.
- Dense-only retrieval from day one — rejected: makes the vertical slice dependent on an external
  API key or a multi-GB local model download before it can run at all, which fails the "runs offline"
  requirement and blocks CI.
