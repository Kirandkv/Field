from __future__ import annotations

from fieldforge_contracts import Citation, GuardrailDecision


def validate_citations(citations: list[Citation], valid_chunk_ids: set[str]) -> GuardrailDecision:
    """Output rail: every citation must resolve to a chunk id that was actually
    retrieved for this query (threat-model row 9, citation fabrication).
    """
    bad = [c.chunk_id for c in citations if c.chunk_id not in valid_chunk_ids]
    return GuardrailDecision(
        rail="output.citation_validation",
        passed=not bad,
        reason=f"citation references unknown chunk id(s): {bad}" if bad else None,
        flagged_spans=bad,
    )


def refusal_response(reason: str) -> str:
    """Output rail: explicit, honest refusal text used when evidence is insufficient
    (threat-model row 9/no-fabrication requirement) — never a guessed answer.
    """
    return f"I don't have enough evidence in the indexed documents to answer this. {reason}"
