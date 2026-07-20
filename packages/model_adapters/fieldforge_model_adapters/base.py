"""Provider-independent answer-generation interface.

Any generative provider (OpenAI-compatible API, Ollama-served local model) implements
this same interface, so apps/docs_api never depends on a specific provider. Slice 1
ships one adapter — ExtractiveAnswerAdapter — which needs no API key and cannot
fabricate text by construction (it only ever emits substrings of retrieved chunks).
A live LLM adapter is planned for M2 (docs/ROADMAP.md P1); it is not stubbed here
un-implemented, per this program's "no half-finished implementations" rule.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from fieldforge_contracts import Citation, RetrievalResult


@dataclass
class GeneratedAnswer:
    text: str
    citations: list[Citation]
    refused: bool
    refusal_reason: str | None = None


class ModelAdapter(ABC):
    name: str

    @abstractmethod
    def generate(self, question: str, evidence: list[RetrievalResult]) -> GeneratedAnswer: ...
