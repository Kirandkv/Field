"""Dense-embedding provider interface.

Provider-independent by design: any real adapter (Ollama-served embedding model, an
OpenAI-compatible endpoint, etc.) implements `EmbeddingAdapter`. Slice 1 ships only
`NullEmbeddingAdapter`, which reports itself unavailable so the retrieval layer can
degrade to BM25-only rather than fail or fabricate a score. Wiring a real adapter is
planned (M2, docs/ROADMAP.md P1) and requires no change to callers of this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingAdapter(ABC):
    @property
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class NullEmbeddingAdapter(EmbeddingAdapter):
    """Default adapter: always unavailable, never called for a real embedding."""

    @property
    def available(self) -> bool:
        return False

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError(
            "NullEmbeddingAdapter has no backing model; check .available before calling embed()"
        )
