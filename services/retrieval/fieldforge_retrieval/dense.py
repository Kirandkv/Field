"""Real local dense retrieval backed by embedded Qdrant — no server, no Docker.
See docs/adr/0005-edge-offline-profile.md decision 1.
"""

from __future__ import annotations

import os

from fieldforge_contracts import Chunk, RetrievalResult
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from fieldforge_retrieval.embedding import EmbeddingAdapter

DEFAULT_QDRANT_PATH = os.getenv("FIELDFORGE_QDRANT_PATH", "./fieldforge_qdrant")
COLLECTION_NAME = "fieldforge_docs_dense"


class QdrantDenseIndex:
    def __init__(self, path: str = DEFAULT_QDRANT_PATH) -> None:
        self._path = path
        self._client: QdrantClient | None = None
        self._chunks_by_point_id: dict[int, Chunk] = {}

    def _ensure_client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(path=self._path)
        return self._client

    @property
    def size(self) -> int:
        return len(self._chunks_by_point_id)

    def build(self, chunks: list[Chunk], embedding_adapter: EmbeddingAdapter) -> None:
        client = self._ensure_client()
        self._chunks_by_point_id = {}
        if client.collection_exists(COLLECTION_NAME):
            client.delete_collection(COLLECTION_NAME)
        if not chunks:
            return

        vectors = embedding_adapter.embed([c.text for c in chunks])
        vector_size = len(vectors[0])
        client.create_collection(
            COLLECTION_NAME, vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
        )

        points = []
        for point_id, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            self._chunks_by_point_id[point_id] = chunk
            points.append(PointStruct(id=point_id, vector=vector, payload={"chunk_id": chunk.id}))
        client.upsert(COLLECTION_NAME, points=points)

    def search(self, query: str, k: int, embedding_adapter: EmbeddingAdapter) -> list[RetrievalResult]:
        if not self._chunks_by_point_id:
            return []
        client = self._ensure_client()
        query_vector = embedding_adapter.embed([query])[0]
        response = client.query_points(COLLECTION_NAME, query=query_vector, limit=k)
        results = []
        for rank, point in enumerate(response.points, start=1):
            chunk = self._chunks_by_point_id.get(int(point.id))
            if chunk is None:
                continue
            results.append(
                RetrievalResult(chunk=chunk, score=float(point.score), rank=rank, retriever="dense")
            )
        return results

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
