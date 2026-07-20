from __future__ import annotations

from fieldforge_contracts import Citation, RetrievalResult, SourceType

from fieldforge_model_adapters.base import GeneratedAnswer, ModelAdapter

MAX_QUOTE_CHARS = 320


class ExtractiveAnswerAdapter(ModelAdapter):
    """Deterministic answer adapter: quotes retrieved chunks verbatim and cites them.

    Cannot hallucinate by construction — every word in the answer is a substring of a
    retrieved, guardrail-passed chunk. This is the honest trade-off documented in
    ADR 0001: a real, weaker answer instead of a fabricated strong one when no LLM
    provider is configured.
    """

    name = "extractive-v1"

    def generate(self, question: str, evidence: list[RetrievalResult]) -> GeneratedAnswer:
        if not evidence:
            return GeneratedAnswer(
                text="",
                citations=[],
                refused=True,
                refusal_reason="no supporting evidence was retrieved for this question",
            )

        citations: list[Citation] = []
        quote_lines: list[str] = []
        for result in evidence:
            quote = result.chunk.text.strip().replace("\n", " ")
            if len(quote) > MAX_QUOTE_CHARS:
                quote = quote[:MAX_QUOTE_CHARS].rsplit(" ", 1)[0] + "..."
            confidence = min(1.0, result.score / (result.score + 1.0)) if result.score > 0 else 0.0
            citations.append(
                Citation(
                    source_type=SourceType.DOCUMENT,
                    source_id=result.chunk.document_id,
                    chunk_id=result.chunk.id,
                    page_number=result.chunk.page_number,
                    quote=quote,
                    retrieval_score=result.score,
                    confidence=confidence,
                    producing_component=self.name,
                )
            )
            doc_ref = f"doc {result.chunk.document_id}, p.{result.chunk.page_number}"
            quote_lines.append(f'"{quote}" ({doc_ref})')

        text = "Based on the indexed documents:\n" + "\n".join(f"- {line}" for line in quote_lines)
        return GeneratedAnswer(text=text, citations=citations, refused=False)
