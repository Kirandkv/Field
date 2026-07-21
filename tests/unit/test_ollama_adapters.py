"""Tests for FieldForge Edge's Ollama-backed adapters.

CI has no Ollama installed, so tests that need a real model call are marked
skipif-unreachable — see docs/adr/0005-edge-offline-profile.md. Tests that exercise
graceful degradation (unreachable host) run everywhere, since that's exactly the
path CI takes.
"""

from __future__ import annotations

import httpx
import pytest
from fieldforge_contracts import Chunk, ChunkingStrategy, RetrievalResult
from fieldforge_model_adapters import ExtractiveAnswerAdapter, OllamaGenerativeAdapter
from fieldforge_retrieval import OllamaEmbeddingAdapter, QdrantDenseIndex
from fieldforge_retrieval.embedding import EmbeddingAdapter

UNREACHABLE_HOST = "http://127.0.0.1:1"


def _ollama_reachable() -> bool:
    try:
        return httpx.get("http://localhost:11434/api/tags", timeout=1.0).status_code == 200
    except httpx.RequestError:
        return False


requires_ollama = pytest.mark.skipif(not _ollama_reachable(), reason="Ollama not reachable on this machine")


def _chunk(text: str, doc_id: str = "doc-1") -> Chunk:
    return Chunk(
        document_id=doc_id,
        page_number=1,
        strategy=ChunkingStrategy.FIXED_TOKEN,
        text=text,
        start_offset=0,
        end_offset=len(text),
        sequence=0,
    )


class FakeEmbeddingAdapter(EmbeddingAdapter):
    """Deterministic, offline embedding stand-in for testing QdrantDenseIndex
    without needing Ollama — real vector-store round-trip, fake vectors.
    """

    @property
    def available(self) -> bool:
        return True

    def embed(self, texts: list[str]) -> list[list[float]]:
        # A trivial, deterministic embedding: bag-of-hashed-words into a fixed-size
        # vector. Good enough to prove the vector store round-trips correctly.
        vectors = []
        for text in texts:
            vec = [0.0] * 16
            for word in text.lower().split():
                vec[hash(word) % 16] += 1.0
            vectors.append(vec)
        return vectors


# --- OllamaEmbeddingAdapter ---


def test_embedding_adapter_unreachable_host_is_unavailable():
    adapter = OllamaEmbeddingAdapter(host=UNREACHABLE_HOST)
    assert adapter.available is False


@requires_ollama
def test_embedding_adapter_real_embed_returns_vectors():
    adapter = OllamaEmbeddingAdapter()
    assert adapter.available is True
    vectors = adapter.embed(["methane sensor calibration"])
    assert len(vectors) == 1
    assert len(vectors[0]) > 0


# --- QdrantDenseIndex (offline, using the fake adapter) ---


def test_dense_index_round_trip_with_fake_embeddings(tmp_path):
    index = QdrantDenseIndex(path=str(tmp_path / "qdrant_test"))
    chunks = [_chunk("methane sensor calibration interval"), _chunk("robot battery and camera")]
    fake = FakeEmbeddingAdapter()
    index.build(chunks, fake)
    assert index.size == 2

    results = index.search("methane sensor calibration", k=2, embedding_adapter=fake)
    assert len(results) == 2
    assert results[0].retriever == "dense"
    index.close()


def test_dense_index_empty_build_search_returns_empty(tmp_path):
    index = QdrantDenseIndex(path=str(tmp_path / "qdrant_empty"))
    index.build([], FakeEmbeddingAdapter())
    assert index.search("anything", k=5, embedding_adapter=FakeEmbeddingAdapter()) == []
    index.close()


# --- OllamaGenerativeAdapter ---


def test_generative_adapter_refuses_with_no_evidence():
    adapter = OllamaGenerativeAdapter()
    answer = adapter.generate("any question", [])
    assert answer.refused is True


def test_generative_adapter_falls_back_when_ollama_unreachable():
    adapter = OllamaGenerativeAdapter(host=UNREACHABLE_HOST, fallback=ExtractiveAnswerAdapter())
    chunk = _chunk("calibration interval is ninety days")
    evidence = [RetrievalResult(chunk=chunk, score=1.0, rank=1, retriever="bm25")]
    answer = adapter.generate("calibration interval?", evidence)
    assert answer.refused is False
    assert answer.citations[0].producing_component == "extractive-v1"


def test_generative_adapter_rejects_citation_with_unknown_chunk_id():
    """Directly exercises the citation guardrail without needing a real model call —
    the fallback triggers because the chunk_id genuinely isn't in the evidence set.
    """
    adapter = OllamaGenerativeAdapter(fallback=ExtractiveAnswerAdapter())
    evidence = [RetrievalResult(chunk=_chunk("real evidence text"), score=1.0, rank=1, retriever="bm25")]
    result = adapter._validate_citations(
        [{"chunk_id": "not-a-real-chunk-id", "quote": "real evidence text"}],
        {r.chunk.id: r for r in evidence},
    )
    assert result is None


def test_generative_adapter_rejects_citation_with_fabricated_quote():
    adapter = OllamaGenerativeAdapter(fallback=ExtractiveAnswerAdapter())
    chunk = _chunk("the actual real evidence text")
    evidence = [RetrievalResult(chunk=chunk, score=1.0, rank=1, retriever="bm25")]
    result = adapter._validate_citations(
        [{"chunk_id": chunk.id, "quote": "something the model made up"}],
        {r.chunk.id: r for r in evidence},
    )
    assert result is None


def test_generative_adapter_accepts_valid_citation():
    adapter = OllamaGenerativeAdapter(fallback=ExtractiveAnswerAdapter())
    chunk = _chunk("the calibration interval is ninety days")
    evidence = [RetrievalResult(chunk=chunk, score=1.0, rank=1, retriever="bm25")]
    result = adapter._validate_citations(
        [{"chunk_id": chunk.id, "quote": "calibration interval is ninety days"}],
        {r.chunk.id: r for r in evidence},
    )
    assert result is not None
    assert result[0].chunk_id == chunk.id


@requires_ollama
def test_generative_adapter_real_call_produces_valid_answer():
    adapter = OllamaGenerativeAdapter(fallback=ExtractiveAnswerAdapter())
    chunk = _chunk(
        "The methane sensor calibration interval for FF-R07 is ninety days, "
        "performed during scheduled maintenance."
    )
    evidence = [RetrievalResult(chunk=chunk, score=2.0, rank=1, retriever="bm25")]
    answer = adapter.generate("What is the calibration interval?", evidence)
    assert answer.refused is False
    assert len(answer.citations) >= 1
    # Whichever component actually produced it (generative or the safe fallback),
    # every citation must resolve to the one real chunk we gave it.
    assert all(c.chunk_id == chunk.id for c in answer.citations)
