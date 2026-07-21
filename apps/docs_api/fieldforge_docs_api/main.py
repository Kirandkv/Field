from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fieldforge_contracts import (
    Chunk,
    Document,
    DocumentStatus,
    GuardrailDecision,
    QueryRequest,
    QueryResponse,
)
from fieldforge_guardrails import (
    scan_query_text,
    scan_retrieved_chunks,
    validate_citations,
    validate_upload,
)
from fieldforge_ingestion import UnsupportedContentType, chunk_pages, extract_pages
from fieldforge_model_adapters import ExtractiveAnswerAdapter, OllamaGenerativeAdapter
from fieldforge_observability import configure_json_logging, get_correlation_id, new_trace_id
from fieldforge_retrieval import BM25Index, OllamaEmbeddingAdapter, QdrantDenseIndex, reciprocal_rank_fusion
from pydantic import BaseModel

from fieldforge_docs_api import edge
from fieldforge_docs_api.config import settings
from fieldforge_docs_api.middleware import CorrelationIdMiddleware
from fieldforge_docs_api.store import DocumentStore

configure_json_logging()
logger = logging.getLogger("fieldforge.docs_api")

app = FastAPI(
    title="FieldForge Docs API",
    version="0.1.0",
    description=(
        "Multimodal document intelligence and advanced RAG for FieldForge Industries. "
        "Slice 1 default: BM25 retrieval + deterministic extractive answers, fully "
        "offline. FieldForge Edge mode (FIELDFORGE_RETRIEVAL_MODE=hybrid, "
        "FIELDFORGE_ANSWER_MODE=generative) adds real local dense retrieval and "
        "generative answers via Ollama — see docs/adr/0005-edge-offline-profile.md."
    ),
)
app.add_middleware(CorrelationIdMiddleware)

store = DocumentStore(settings.db_path)
index = BM25Index()

hybrid_enabled = settings.retrieval_mode == "hybrid"
embedding_adapter = OllamaEmbeddingAdapter(host=settings.ollama_host) if hybrid_enabled else None
dense_index = QdrantDenseIndex(path=settings.qdrant_path) if hybrid_enabled else None

answer_adapter = (
    OllamaGenerativeAdapter(host=settings.ollama_host, fallback=ExtractiveAnswerAdapter())
    if settings.answer_mode == "generative"
    else ExtractiveAnswerAdapter()
)


def _rebuild_index() -> None:
    chunks: list[Chunk] = store.all_chunks()
    index.build(chunks)
    logger.info("sparse index rebuilt", extra={"extra_fields": {"chunk_count": len(chunks)}})

    if dense_index is not None and embedding_adapter is not None:
        if embedding_adapter.available:
            dense_index.build(chunks, embedding_adapter)
            logger.info("dense index rebuilt", extra={"extra_fields": {"chunk_count": len(chunks)}})
        else:
            logger.warning(
                "hybrid retrieval mode requested but Ollama embedding model is "
                "unavailable — degrading to sparse-only for this query cycle",
            )


_rebuild_index()


@app.on_event("shutdown")
def _shutdown() -> None:
    store.close()
    if dense_index is not None:
        dense_index.close()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "indexed_chunks": index.size,
        "documents": len(store.list_documents()),
        "retrieval_mode": settings.retrieval_mode,
        "answer_mode": settings.answer_mode,
        "dense_available": bool(embedding_adapter and embedding_adapter.available),
    }


@app.get("/documents")
def list_documents() -> list[Document]:
    return store.list_documents()


@app.get("/documents/{document_id}")
def get_document(document_id: str) -> Document:
    doc = store.get_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"document {document_id} not found")
    return doc


@app.post("/documents", status_code=201)
async def upload_document(file: UploadFile = File(...)) -> Document:  # noqa: B008 (FastAPI idiom)
    raw = await file.read()
    filename = file.filename or "unnamed"
    content_type = file.content_type or "application/octet-stream"

    upload_decision = validate_upload(filename, content_type, len(raw), settings.max_upload_bytes)
    if not upload_decision.passed:
        raise HTTPException(status_code=400, detail=upload_decision.reason)

    sha256 = hashlib.sha256(raw).hexdigest()
    existing = store.sha256_exists(sha256)
    if existing is not None:
        logger.info(
            "duplicate upload detected", extra={"extra_fields": {"document_id": existing.id}}
        )
        return existing

    # Content-addressed id: makes duplicate detection trivial and gives evaluation
    # datasets a stable document reference across runs (see evals/datasets).
    doc = Document(id=sha256, filename=filename, content_type=content_type, sha256=sha256)
    try:
        pages = extract_pages(doc.id, content_type, raw)
    except UnsupportedContentType as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # extraction failure -> FAILED status, not a silent drop
        doc = doc.model_copy(update={"status": DocumentStatus.FAILED, "error": str(exc)})
        store.save_document(doc)
        logger.error(
            "extraction failed",
            extra={"extra_fields": {"document_id": doc.id, "error": str(exc)}},
        )
        return doc

    chunks = chunk_pages(pages)
    doc = doc.model_copy(update={"status": DocumentStatus.INDEXED, "page_count": len(pages)})
    store.save_document(doc)
    store.save_pages(pages)
    store.save_chunks(chunks)
    _rebuild_index()

    logger.info(
        "document ingested",
        extra={"extra_fields": {"document_id": doc.id, "pages": len(pages), "chunks": len(chunks)}},
    )
    return doc


@app.post("/query")
def query(request: QueryRequest) -> QueryResponse:
    start = time.perf_counter()
    trace_id = get_correlation_id() or new_trace_id()
    decisions: list[GuardrailDecision] = []

    input_decisions = scan_query_text(request.question)
    decisions.extend(input_decisions)
    blocking = [d for d in input_decisions if not d.passed]
    if blocking:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "query blocked by input guardrails",
                "reasons": [d.reason for d in blocking],
            },
        )

    sparse_results = index.search(request.question, k=request.k)
    raw_results = sparse_results
    if dense_index is not None and embedding_adapter is not None and dense_index.size > 0:
        dense_results = dense_index.search(request.question, k=request.k, embedding_adapter=embedding_adapter)
        raw_results = reciprocal_rank_fusion([sparse_results, dense_results])[: request.k]

    clean_results, retrieval_decisions = scan_retrieved_chunks(raw_results)
    decisions.extend(retrieval_decisions)

    generated = answer_adapter.generate(request.question, clean_results)

    if generated.refused:
        latency_ms = (time.perf_counter() - start) * 1000
        return QueryResponse(
            trace_id=trace_id,
            answer=(
                "I don't have enough evidence in the indexed documents to answer this. "
                f"{generated.refusal_reason}"
            ),
            refused=True,
            citations=[],
            guardrail_decisions=decisions,
            latency_ms=round(latency_ms, 2),
        )

    valid_chunk_ids = {r.chunk.id for r in clean_results}
    citation_decision = validate_citations(generated.citations, valid_chunk_ids)
    decisions.append(citation_decision)
    if not citation_decision.passed:
        # A citation referencing a chunk outside this query's retrieved set is treated as
        # unverifiable and dropped rather than shown — see threat-model row 9.
        raise HTTPException(status_code=500, detail="internal citation validation failure")

    latency_ms = (time.perf_counter() - start) * 1000
    return QueryResponse(
        trace_id=trace_id,
        answer=generated.text,
        refused=False,
        citations=generated.citations,
        guardrail_decisions=decisions,
        latency_ms=round(latency_ms, 2),
    )


# --- FieldForge Edge: resource monitoring + backup/restore ---
# See docs/adr/0005-edge-offline-profile.md. Real, working, but not required —
# these endpoints work regardless of retrieval_mode/answer_mode.


@app.get("/edge/resources")
def edge_resources() -> dict:
    return edge.get_resource_snapshot(settings.ollama_host)


@app.post("/edge/backup", status_code=201)
def edge_backup() -> dict:
    backup_path = f"{settings.backup_dir}/backup-{int(time.time())}.sqlite3"
    store.backup_to(backup_path)
    logger.info("backup created", extra={"extra_fields": {"backup_path": backup_path}})
    return {"backup_path": backup_path}


class RestoreRequest(BaseModel):
    backup_path: str


@app.post("/edge/restore")
def edge_restore(body: RestoreRequest) -> dict:
    # Confine restore to files inside the configured backup directory — otherwise a
    # caller could point this at any SQLite-openable file the process can read and
    # overwrite the live database with its contents. See docs/threat-model/THREAT_MODEL.md.
    backup_root = Path(settings.backup_dir).resolve()
    requested = Path(body.backup_path).resolve()
    if backup_root != requested and backup_root not in requested.parents:
        raise HTTPException(
            status_code=400, detail=f"backup_path must be inside {settings.backup_dir}"
        )
    try:
        store.restore_from(str(requested))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _rebuild_index()
    logger.info("database restored", extra={"extra_fields": {"backup_path": str(requested)}})
    return {"status": "restored", "backup_path": str(requested)}
