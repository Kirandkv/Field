# Threat Model — FieldForge Docs (Slice 1)

Scope: this document covers what is **implemented** in slice 1. Threats relevant to agents/tools/A2A
(Copilot, Mesh) are listed for suite-level completeness but marked **N/A (not built)** since those
components don't exist yet — listing them now avoids retrofitting security review later.

Methodology: STRIDE-flavored, enumerated against the suite's required threat list.

| # | Threat | Status | Mitigation (implemented) | Mitigation (planned) |
|---|---|---|---|---|
| 1 | Direct prompt injection (user asks model to ignore instructions/reveal system prompt) | Implemented | Input rail scans query text for known injection patterns before retrieval; extractive adapter has no system prompt to leak (it does not call an LLM) | When a live LLM adapter ships (M2), re-validate this rail against it specifically |
| 2 | Indirect prompt injection (instructions hidden inside an ingested document, e.g. white text, fake "SYSTEM:" lines) | Implemented | Retrieval rail scans every retrieved chunk for imperative-toward-the-model patterns (`ignore previous`, `system:`, `you must now`, etc.) before the chunk reaches the answer step; matches are flagged and excluded, not executed | Expand pattern set from real adversarial eval results |
| 3 | Retrieval poisoning (malicious/incorrect doc ranks highly) | Partial | BM25 scores are deterministic and inspectable; `EvaluationCase` set includes adversarial fixtures | Trusted-source allowlist + doc-version filtering at M2 |
| 4 | Tool misuse | N/A (no tools in slice 1) | — | Tool allowlists by agent/role — Copilot milestone |
| 5 | Excessive agency | N/A (no agent in slice 1) | — | Max-steps, max-tool-calls, budgets — Copilot milestone |
| 6 | Cross-agent privilege escalation | N/A (no multi-agent in slice 1) | — | Mesh milestone: per-agent permission matrix |
| 7 | Data exfiltration via answer text | Implemented | Output rail rejects answers containing content not traceable to a retrieved chunk (extractive-only generation makes fabrication structurally impossible in this slice) | Broaden once a generative LLM adapter is live — faithfulness scoring becomes load-bearing then |
| 8 | Malicious file ingestion (oversized file, wrong type, zip bomb, path traversal via filename) | Implemented | Input rail: extension allowlist, size cap, filename sanitization before any parsing; upload path never trusts the client-supplied filename for storage | Sandboxed parsing process / antivirus scan for M2 |
| 9 | Citation fabrication | Implemented | Every citation is generated from the actual `chunk_id`/`page` used in the answer; output rail rejects any citation whose id doesn't resolve in the current index | — |
| 10 | Denial-of-wallet | N/A (no paid API calls in slice 1 default path) | Default adapters make zero external calls | Token/cost budget enforcement once a paid LLM adapter is wired |
| 11 | Infinite agent loops | N/A (no agent loop in slice 1) | — | Max-steps + loop detection — Copilot milestone |
| 12 | Unauthorized A2A delegation | N/A (no A2A in slice 1) | — | Mesh milestone |
| 13 | Approval bypass | N/A (no state-changing actions in slice 1 — Docs is read-only) | — | Copilot milestone: approval required for all state-changing tools |
| 14 | PII / secret leakage from uploaded docs into logs or answers | Implemented | Input rail regex-detects common secret shapes (API keys, AWS-style keys, private key headers) and PII shapes (email, phone, SSN-like patterns) in uploaded text; matches are redacted in logs; synthetic corpus intentionally contains zero real PII | Configurable redaction policy per role at auth milestone |
| 15 | Denial of service via oversized query/response | Implemented | Request body size limit; max retrieved chunks (`k`) bounded; max response size bounded | Rate limiting per API key — auth milestone |

## Out of scope for slice 1 (tracked, not silently dropped)

Guardrail categories from the program brief not yet applicable because their subject doesn't exist
yet: tool allowlists, parameter bounds, state-transition validation, idempotency keys, sandboxed
writes, MCP server availability, A2A message schema validation. These become in-scope threat rows
the moment Copilot/Mesh are implemented — see [ROADMAP.md](../ROADMAP.md).

## Guardrail evaluation coverage (slice 1)

Adversarial fixtures for rows 1, 2, 8, 9, 14 above live in
[evals/datasets/guardrails_docs_v1.jsonl](../../evals/datasets/guardrails_docs_v1.jsonl) and are
scored by [evals/scorers](../../evals/scorers). Results: see
[evals/reports](../../evals/reports).
