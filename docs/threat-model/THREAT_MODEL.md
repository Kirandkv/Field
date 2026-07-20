# Threat Model — FieldForge Docs + Copilot (Slice 1)

Scope: this document covers what is **implemented** across FieldForge Docs and FieldForge Copilot
slice 1. Threats relevant to A2A/multi-agent (Mesh) are listed for suite-level completeness but
marked **N/A (not built)** since Mesh doesn't exist yet — listing them now avoids retrofitting
security review later.

Methodology: STRIDE-flavored, enumerated against the suite's required threat list.

| # | Threat | Status | Mitigation (implemented) | Mitigation (planned) |
|---|---|---|---|---|
| 1 | Direct prompt injection (user asks model to ignore instructions/reveal system prompt) | Implemented | Input rail scans query text for known injection patterns before retrieval; extractive adapter has no system prompt to leak (it does not call an LLM) | When a live LLM adapter ships (M2), re-validate this rail against it specifically |
| 2 | Indirect prompt injection (instructions hidden inside an ingested document, e.g. white text, fake "SYSTEM:" lines) | Implemented | Retrieval rail scans every retrieved chunk for imperative-toward-the-model patterns (`ignore previous`, `system:`, `you must now`, etc.) before the chunk reaches the answer step; matches are flagged and excluded, not executed | Expand pattern set from real adversarial eval results |
| 3 | Retrieval poisoning (malicious/incorrect doc ranks highly) | Partial | BM25 scores are deterministic and inspectable; `EvaluationCase` set includes adversarial fixtures | Trusted-source allowlist + doc-version filtering at M2 |
| 4 | Tool misuse | Partial | Copilot's tools are read-only except `create_maintenance_ticket`, which never runs from agent code — only from the API layer, only after a stored human decision (see row 13) | Explicit per-tool allowlist-by-role once Copilot has >1 role-differentiated caller |
| 5 | Excessive agency | Partial | Copilot's state machine is a single deterministic pass (RECEIVED → terminal) with no loop construct at all — there is no code path that lets the agent call more tools than the fixed sequence in `orchestrator.investigate()` | Explicit max-steps/max-tool-calls counters become meaningful once Mesh introduces multi-step delegation |
| 6 | Cross-agent privilege escalation | N/A (no multi-agent in slice 1) | — | Mesh milestone: per-agent permission matrix |
| 7 | Data exfiltration via answer text | Implemented | Docs: output rail rejects answers not traceable to a retrieved chunk. Copilot: `reasoning_summary` is built from the same evidence objects returned to the client — no hidden model output exists to exfiltrate (there is no LLM call in either product's default path) | Broaden once a generative LLM adapter is live — faithfulness scoring becomes load-bearing then |
| 8 | Malicious file ingestion (oversized file, wrong type, zip bomb, path traversal via filename) | Implemented | Input rail: extension allowlist, size cap, filename sanitization before any parsing; upload path never trusts the client-supplied filename for storage | Sandboxed parsing process / antivirus scan for M2 |
| 9 | Citation fabrication | Implemented | Docs: every citation resolves to a real `chunk_id`. Copilot: SOP evidence is a direct pass-through of Docs' own citations, not re-generated | — |
| 10 | Denial-of-wallet | N/A (no paid API calls in slice 1 default path) | Default adapters make zero external calls; Copilot's only outbound call (`retrieve_sop`) hits a peer service on localhost, not a paid API | Token/cost budget enforcement once a paid LLM adapter is wired |
| 11 | Infinite agent loops | N/A | Copilot has no loop construct (see row 5); `REQUESTING_MORE_EVIDENCE` is a terminal state in slice 1 specifically to avoid an automatic retry loop — see ADR 0002 | Loop detection becomes necessary once retry/escalation logic is added (M2) |
| 12 | Unauthorized A2A delegation | N/A (no A2A in slice 1) | — | Mesh milestone |
| 13 | Approval bypass | Implemented (Copilot) | `POST /approvals/{id}/decision` requires `X-FieldForge-Role: safety_manager`, checked server-side; rejected server responses never advance the incident's state. Tested: `tests/integration/test_copilot_api.py::test_decision_without_role_header_is_rejected` and `::test_decision_with_wrong_role_is_rejected`, plus `evals/datasets/copilot_scenarios_v1.jsonl` cop-009/cop-010 (unauthorized_action_prevention_rate) | Full 5-role matrix across every endpoint — shared M2 item with Docs |
| 14 | PII / secret leakage from uploaded docs into logs or answers | Implemented | Input rail regex-detects common secret shapes (API keys, AWS-style keys, private key headers) and PII shapes (email, phone, SSN-like patterns) in uploaded text; matches are redacted in logs; synthetic corpus intentionally contains zero real PII | Configurable redaction policy per role at auth milestone |
| 15 | Denial of service via oversized query/response | Implemented (Docs) | Request body size limit; max retrieved chunks (`k`) bounded; max response size bounded | Rate limiting per API key — auth milestone; apply the same bounds to Copilot's `/alerts` |
| 16 | Tool timeout / unreachable dependency (Copilot's `retrieve_sop` calling a peer service) | Implemented | 5s HTTP timeout on the Docs API call; connection failure returns `ToolStatus.UNAVAILABLE`, and the state machine proceeds with degraded evidence rather than blocking or crashing — see `tests/unit/test_orchestrator.py::test_investigation_completes_without_crashing_when_docs_api_unavailable` | — |
| 17 | Idempotency / replayed approval decision | Implemented | An `ApprovalRequest` can be decided exactly once (`decided` flag checked server-side); a second decision attempt on the same id returns 409, tested in `tests/integration/test_copilot_api.py::test_deciding_an_already_decided_approval_is_rejected` | Idempotency keys on `/alerts` submission itself (duplicate alert detection) — planned M2 |

## Out of scope for slice 1 (tracked, not silently dropped)

Guardrail categories from the program brief not yet applicable because their subject doesn't exist
yet: tool allowlists, parameter bounds, state-transition validation, idempotency keys, sandboxed
writes, MCP server availability, A2A message schema validation. These become in-scope threat rows
the moment Copilot/Mesh are implemented — see [ROADMAP.md](../ROADMAP.md).

## Guardrail evaluation coverage (slice 1)

Docs adversarial fixtures for rows 1, 2, 8, 9, 14 live in
[evals/datasets/guardrails_docs_v1.jsonl](../../evals/datasets/guardrails_docs_v1.jsonl), scored by
[evals/scorers](../../evals/scorers). Copilot's rows 4, 5, 11, 13, 16, 17 are covered by
[evals/datasets/copilot_scenarios_v1.jsonl](../../evals/datasets/copilot_scenarios_v1.jsonl)
(`unauthorized_action_prevention_rate`, `recovery_after_failure_rate`) plus the integration tests
cited inline above. Results for both: [evals/reports](../../evals/reports).
