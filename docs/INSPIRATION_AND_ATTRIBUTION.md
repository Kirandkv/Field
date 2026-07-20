# Inspiration and Attribution

## Supplied inspiration repositories

None were attached or linked in this session. No external repository was inspected, forked, or
copied from. This document is created per the program's originality process so the obligation is
tracked from day one; it will be updated the moment any inspiration repository is actually
supplied and reviewed.

## What was studied

- The publicly documented shapes of common OSS patterns this codebase necessarily resembles by
  convention rather than by copying — e.g. FastAPI's own dependency-injection idioms, BM25's
  standard Okapi formula (a public-domain algorithm, not any one project's code), and RRF as
  published in Cormack et al., 2009 ("Reciprocal Rank Fusion outperforms Condorcet and individual
  Rank Learning Methods"). These are algorithms/APIs, not source code, and are implemented
  independently in this repo.

## What was adopted

- Standard architectural pattern: separate ingestion / retrieval / guardrails / generation /
  API layers, each independently testable. This is a widely-published RAG pattern, not sourced
  from a specific project.

## What code was reused

- None. `rank_bm25` and `pypdf` (or equivalent) are used as declared pip dependencies under their
  own licenses (see `pyproject.toml` / `requirements.txt` for exact packages and versions) —
  they are called via their public API, not vendored or copied into this repo.

## What was independently reimplemented

- Fixed-token chunker, extraction pipeline glue, guardrail regex layer, extractive answer
  adapter, correlation-ID/logging middleware, evaluation scorer (Recall@k, MRR, citation
  correctness) — all written for this repo, not derived from a reference implementation.

## How this project differs materially

- Domain: synthetic industrial fleet-operations corpus (FieldForge Industries), not a generic
  document-QA demo dataset.
- Default posture: offline-first, dependency-light BM25 baseline with measured metrics, rather
  than a dense-retrieval-only demo that requires a paid API key to show any result.
- Guardrails are wired into the retrieval path from slice 1 (indirect-injection scanning on
  retrieved chunks), not bolted on after a "does it work" milestone.

## Third-party licenses in use

Tracked exactly in the lock file / `pyproject.toml`. As of slice 1: `fastapi`, `pydantic`,
`rank-bm25`, `pypdf`, `uvicorn`, `pytest` — all permissively licensed (MIT/BSD/Apache-2.0).
No copyleft dependency is used. Re-verify with a license-checker in CI (see
`.github/workflows/pr.yml`) rather than trusting this static note as time passes.
