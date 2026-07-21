"""Real local dense-embedding adapter backed by Ollama.

Implements the `EmbeddingAdapter` interface defined in embedding.py — this is the
"planned M2" adapter ADR 0001 deferred, now wired for FieldForge Edge. See
docs/adr/0005-edge-offline-profile.md.
"""

from __future__ import annotations

import os

import httpx

from fieldforge_retrieval.embedding import EmbeddingAdapter

DEFAULT_HOST = os.getenv("FIELDFORGE_OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("FIELDFORGE_OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")


class OllamaEmbeddingAdapter(EmbeddingAdapter):
    def __init__(self, host: str = DEFAULT_HOST, model: str = DEFAULT_MODEL, timeout: float = 30.0) -> None:
        self._host = host
        self._model = model
        self._timeout = timeout

    @property
    def available(self) -> bool:
        try:
            resp = httpx.get(f"{self._host}/api/tags", timeout=2.0)
        except httpx.RequestError:
            return False
        if resp.status_code != 200:
            return False
        pulled = {m["name"] for m in resp.json().get("models", [])}
        # Ollama tags include a version suffix (e.g. "nomic-embed-text:latest");
        # match on the base name too so a bare model name in config still resolves.
        pulled_base = {name.split(":")[0] for name in pulled}
        return self._model in pulled or self._model.split(":")[0] in pulled_base

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            try:
                resp = httpx.post(
                    f"{self._host}/api/embeddings",
                    json={"model": self._model, "prompt": text},
                    timeout=self._timeout,
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise RuntimeError(
                    f"Ollama embedding request failed for model {self._model!r}: {exc}"
                ) from exc
            vectors.append(resp.json()["embedding"])
        return vectors
