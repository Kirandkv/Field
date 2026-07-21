# ADR 0005: Edge offline profile — embedded Qdrant, Ollama, config-toggle architecture

- Status: Accepted
- Date: 2026-07-21

## Context

FieldForge Edge (milestone M6, optional per the program brief) is an offline
deployment profile for Docs — local models, local vector store, no cloud call. It
also happens to fill two gaps Docs' own roadmap deferred to "M2": dense/hybrid
retrieval and a live LLM adapter (see [ADR 0001](0001-monorepo-vertical-slice.md)).
This slice was only attempted because both dependencies verify as actually usable
in this environment: Ollama is installed and running locally with `nomic-embed-text`
and several chat models already pulled, and `qdrant-client`'s embedded local mode
(`QdrantClient(path=...)`) works standalone with no server or Docker.

## Decisions

1. **Qdrant runs embedded (local file-backed), not as a server.** The program brief
   lists "local Qdrant" as an Edge requirement; `qdrant-client`'s `path=` mode is a
   genuine local vector store with no network dependency, verified working before
   committing to this design. A real Docker-based Qdrant server is a plausible M2
   upgrade for the eventual full Docs deployment (ADR 0001), but Edge specifically
   wants zero infrastructure beyond the Python process.

2. **The default local generation model is `qwen2.5:0.5b`, embeddings are
   `nomic-embed-text`.** Both were already present on this development machine.
   Measured on this machine's CPU: 46.9 tokens/sec warm generation, ~0.35s warm
   embedding latency (cold-start ~6-7s for either, which is the model being loaded
   into memory — see [EDGE_OVERVIEW.md](../architecture/EDGE_OVERVIEW.md) for the
   full numbers). Both model names are configurable via environment variable —
   nothing is hardcoded to this specific pull.

3. **Edge is a configuration toggle on FieldForge Docs, not a new service.** The
   program brief calls Edge "an offline deployment package for FieldForge Docs,"
   not a sixth product. `FIELDFORGE_RETRIEVAL_MODE` (`sparse` default | `hybrid`)
   and `FIELDFORGE_ANSWER_MODE` (`extractive` default | `generative`) select the
   adapters `apps/docs_api` wires up at startup. The default is unchanged from
   slice 1 — every existing Docs test still exercises the exact same code path it
   always did. Edge mode is additive, opt-in, and never required.

4. **Generative answers are guardrailed by construction, not by trust.**
   `OllamaGenerativeAdapter` requires the model to respond in strict JSON
   (`{"answer": ..., "citations": [{"chunk_id": ..., "quote": ...}]}`). The output
   rail then verifies every `chunk_id` resolves to an actually-retrieved chunk *and*
   every `quote` is a real substring of that chunk's text — not just a plausible
   citation, an actually-checked one. If the model returns invalid JSON, an unknown
   `chunk_id`, or a quote that isn't really in the source, the adapter **falls back
   to the existing deterministic `ExtractiveAnswerAdapter`** rather than surfacing
   an unverified generative answer. This is the same "no unsupported claims"
   posture as slice 1, extended to cover a component (a small local LLM) that can
   actually hallucinate, unlike the purely extractive default.

5. **Hardware-profile benchmarking is honest about what wasn't measured.** This
   development environment has no GPU and no Jetson device. Only the CPU-only
   profile is measured; GPU and Jetson rows in the benchmark table are `TBD`, not
   estimated or extrapolated — see the program brief's explicit prohibition on
   invented benchmark values.

6. **Encrypted storage, local audit log, and cloud-sync-conflict simulation are
   deferred, not built.** Encrypting existing Docs SQLite fields would touch
   already-committed, already-tested code broadly for a slice-1 feature with no
   real threat it defends against yet (no multi-tenant deployment exists). A local
   audit log duplicates what Ops already does at the suite level. Cloud-sync
   conflict simulation has no real cloud deployment to conflict with — simulating
   one would be exactly the "fake terminal animation" the program brief prohibits.
   All three are real, trackable M2 items, not silently dropped — see
   [docs/ROADMAP.md](../ROADMAP.md).

## A real bug this design caught

`apps/docs_api` originally instantiated `OllamaEmbeddingAdapter()`/`OllamaGenerativeAdapter()`
with no explicit host, relying on each adapter's constructor default (itself a
module-level constant read from `FIELDFORGE_OLLAMA_HOST` once, at first import).
A test that set `FIELDFORGE_OLLAMA_HOST` and reloaded the app module found that the
override silently had no effect — the already-imported module's constant stayed
frozen from whenever it was first imported in the process. Fixed by adding
`ollama_host` to `Settings` (re-read fresh on every `Settings()` construction, which
tests already reload) and passing it explicitly into every adapter constructor —
see `tests/integration/test_docs_api_edge_mode.py::test_edge_resources_endpoint_works_without_ollama`.

## Consequences

- Positive: Docs can now answer generatively with real local inference, entirely
  offline, with a citation guardrail that's actually enforced rather than
  described. This is real progress on two items ADR 0001 explicitly deferred.
- Positive: zero regression risk — every existing test still runs the unmodified
  slice-1 default path; Edge is purely additive configuration.
- Negative: CI has no Ollama installed, so Edge-specific tests must skip (not
  fail) when Ollama is unreachable — real coverage only runs where Ollama is
  actually present (this development machine, or a contributor's own setup). This
  is disclosed in `tests/unit/test_ollama_adapters.py` and the CI workflow, not
  hidden behind a passing-by-omission test suite.
- Negative: "hardware profile" claims are CPU-only for this slice — a reviewer
  cannot assume GPU/Jetson numbers exist just because the brief asked for them.
