"""Real local generative answer adapter backed by Ollama.

Unlike ExtractiveAnswerAdapter, this adapter can genuinely hallucinate — it's a real
LLM, even a small local one. The output rail below is not decorative: every
citation's chunk_id and quote are checked against the actual retrieved evidence
before the answer is trusted. Any failure (invalid JSON, unknown chunk_id, a quote
that isn't really in the source, or an unreachable Ollama server) falls back to the
deterministic ExtractiveAnswerAdapter rather than surfacing an unverified answer.
See docs/adr/0005-edge-offline-profile.md decision 4.
"""

from __future__ import annotations

import json
import os
import re

import httpx
from fieldforge_contracts import Citation, RetrievalResult, SourceType

from fieldforge_model_adapters.base import GeneratedAnswer, ModelAdapter
from fieldforge_model_adapters.extractive import ExtractiveAnswerAdapter

DEFAULT_HOST = os.getenv("FIELDFORGE_OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("FIELDFORGE_OLLAMA_GENERATION_MODEL", "qwen2.5:0.5b")
MAX_CONTEXT_CHARS_PER_CHUNK = 500

_PROMPT_TEMPLATE = """You answer questions using ONLY the numbered evidence below. \
Respond with strict JSON and nothing else, in this exact shape:
{{"answer": "your answer text", "citations": [{{"chunk_id": "<id>", "quote": "<exact substring>"}}]}}

Rules:
- Only use information present in the evidence below.
- Every claim must be backed by at least one citation.
- "quote" must be an exact, verbatim substring of the cited chunk's text.
- If the evidence does not answer the question, set "answer" to "" and "citations" to [].

Evidence:
{evidence_block}

Question: {question}

JSON response:"""


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class OllamaGenerativeAdapter(ModelAdapter):
    name = "ollama-generative-v1"

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
        fallback: ModelAdapter | None = None,
    ) -> None:
        self._host = host
        self._model = model
        self._timeout = timeout
        self._fallback = fallback or ExtractiveAnswerAdapter()

    def generate(self, question: str, evidence: list[RetrievalResult]) -> GeneratedAnswer:
        if not evidence:
            return GeneratedAnswer(
                text="", citations=[], refused=True, refusal_reason="no supporting evidence was retrieved"
            )

        by_chunk_id = {r.chunk.id: r for r in evidence}
        prompt = self._build_prompt(question, evidence)

        try:
            resp = httpx.post(
                f"{self._host}/api/generate",
                json={"model": self._model, "prompt": prompt, "format": "json", "stream": False},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            raw_response = resp.json()["response"]
            parsed = json.loads(raw_response)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError):
            return self._fallback.generate(question, evidence)

        answer_text = parsed.get("answer") if isinstance(parsed, dict) else None
        raw_citations = parsed.get("citations") if isinstance(parsed, dict) else None
        if not answer_text or not isinstance(raw_citations, list) or not raw_citations:
            return self._fallback.generate(question, evidence)

        validated_citations = self._validate_citations(raw_citations, by_chunk_id)
        if validated_citations is None:
            # At least one citation didn't check out — don't trust a partially
            # unverifiable answer. Fall back rather than silently dropping the bad
            # citation and keeping the rest.
            return self._fallback.generate(question, evidence)

        return GeneratedAnswer(text=answer_text, citations=validated_citations, refused=False)

    def _build_prompt(self, question: str, evidence: list[RetrievalResult]) -> str:
        lines = []
        for i, result in enumerate(evidence, start=1):
            text = result.chunk.text.strip()[:MAX_CONTEXT_CHARS_PER_CHUNK]
            lines.append(f'[{i}] chunk_id="{result.chunk.id}": {text}')
        return _PROMPT_TEMPLATE.format(evidence_block="\n".join(lines), question=question)

    def _validate_citations(
        self, raw_citations: list, by_chunk_id: dict[str, RetrievalResult]
    ) -> list[Citation] | None:
        citations: list[Citation] = []
        for raw in raw_citations:
            if not isinstance(raw, dict):
                return None
            chunk_id = raw.get("chunk_id")
            quote = raw.get("quote")
            if not chunk_id or not quote or chunk_id not in by_chunk_id:
                return None
            result = by_chunk_id[chunk_id]
            if _normalize_whitespace(quote) not in _normalize_whitespace(result.chunk.text):
                return None  # the model claimed a quote that isn't actually in the source
            confidence = min(1.0, result.score / (result.score + 1.0)) if result.score > 0 else 0.5
            citations.append(
                Citation(
                    source_type=SourceType.DOCUMENT,
                    source_id=result.chunk.document_id,
                    chunk_id=chunk_id,
                    page_number=result.chunk.page_number,
                    quote=quote,
                    retrieval_score=result.score,
                    confidence=confidence,
                    producing_component=self.name,
                )
            )
        return citations
