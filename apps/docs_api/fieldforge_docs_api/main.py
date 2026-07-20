from __future__ import annotations

import hashlib
import logging
import time

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
from fieldforge_model_adapters import ExtractiveAnswerAdapter
from fieldforge_observability import configure_json_logging, get_correlation_id, new_trace_id
from fieldforge_retrieval import BM25Index

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
        "Slice 1: BM25 retrieval + deterministic extractive answers, fully offline."
    ),
)
app.add_middleware(CorrelationIdMiddleware)

store = DocumentStore(settings.db_path)
index = BM25Index()
answer_adapter = ExtractiveAnswerAdapter()


def _rebuild_index() -> None:
    chunks: list[Chunk] = store.all_chunks()
    index.build(chunks)
    logger.info("index rebuilt", extra={"extra_fields": {"chunk_count": len(chunks)}})


_rebuild_index()


@app.on_event("shutdown")
def _shutdown() -> None:
    store.close()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "indexed_chunks": index.size, "documents": len(store.list_documents())}


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

    raw_results = index.search(request.question, k=request.k)
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
