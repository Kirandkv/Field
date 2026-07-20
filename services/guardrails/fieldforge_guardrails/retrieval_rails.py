from __future__ import annotations

from fieldforge_contracts import GuardrailDecision, RetrievalResult

from fieldforge_guardrails.patterns import find_injection_spans


def scan_retrieved_chunks(
    results: list[RetrievalResult],
) -> tuple[list[RetrievalResult], list[GuardrailDecision]]:
    """Retrieval rail: detect instructions embedded inside retrieved document content
    (threat-model row 2, indirect prompt injection). Flagged chunks are excluded from
    what reaches the answer step, not "trusted but noted" — the point of this rail is
    that document text is data, never instructions.
    """
    clean: list[RetrievalResult] = []
    decisions: list[GuardrailDecision] = []
    for result in results:
        spans = find_injection_spans(result.chunk.text)
        if spans:
            decisions.append(
                GuardrailDecision(
                    rail="retrieval.injection_scan",
                    passed=False,
                    reason=f"embedded instruction pattern in chunk {result.chunk.id}",
                    flagged_spans=spans,
                )
            )
            continue
        clean.append(result)
    if not decisions:
        decisions.append(GuardrailDecision(rail="retrieval.injection_scan", passed=True))
    return clean, decisions
