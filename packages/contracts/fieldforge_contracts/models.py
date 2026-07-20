"""Shared typed contracts for the FieldForge AI Suite.

Slice 1 (FieldForge Docs) implements the subset needed for ingestion, retrieval, and
grounded answering. Contracts for Copilot/Mesh (Device, Sensor, TelemetryPoint, Alert,
Incident, AgentTask, ApprovalRequest, ...) are added when those milestones start —
see docs/ROADMAP.md. Keeping unused contracts out of this file avoids speculative
schemas nobody has validated against real code.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid.uuid4().hex


class SourceType(StrEnum):
    """Where a piece of evidence came from — required on every evidence item."""

    DOCUMENT = "document"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class ChunkingStrategy(StrEnum):
    FIXED_TOKEN = "fixed_token"
    # Additional strategies (recursive, sentence_aware, semantic, layout_aware,
    # parent_child, table_aware, small_to_big) are planned for the M2 chunking
    # benchmark — see docs/ROADMAP.md P1.


class Document(BaseModel):
    """A single ingested source document."""

    id: str = Field(default_factory=_new_id)
    filename: str
    content_type: str
    language: str = "en"
    version: int = 1
    status: DocumentStatus = DocumentStatus.UPLOADED
    page_count: int | None = None
    sha256: str
    uploaded_at: datetime = Field(default_factory=_utcnow)
    error: str | None = None

    @field_validator("filename")
    @classmethod
    def _no_path_traversal(cls, v: str) -> str:
        if "/" in v or "\\" in v or v.startswith("."):
            raise ValueError("filename must not contain path separators or start with '.'")
        return v


class DocumentPage(BaseModel):
    """One page of extracted text from a Document, with provenance."""

    id: str = Field(default_factory=_new_id)
    document_id: str
    page_number: int
    text: str
    ocr_confidence: float | None = None  # None until OCR fallback exists (M2)


class Chunk(BaseModel):
    """A retrievable unit of text, produced by a chunking strategy."""

    id: str = Field(default_factory=_new_id)
    document_id: str
    page_number: int
    strategy: ChunkingStrategy
    text: str
    start_offset: int
    end_offset: int
    sequence: int


class Citation(BaseModel):
    """Provenance for a single claim in a generated answer.

    Every evidence item in the suite must carry: source type, source id, timestamp,
    confidence, retrieval score (where applicable), page/interval, and producing
    component — enforced here as required fields, not optional extras.
    """

    source_type: SourceType
    source_id: str  # document_id
    chunk_id: str
    page_number: int
    quote: str
    retrieval_score: float
    confidence: float
    producing_component: str
    timestamp: datetime = Field(default_factory=_utcnow)


class RetrievalResult(BaseModel):
    """One scored chunk returned by the retrieval layer."""

    chunk: Chunk
    score: float
    rank: int
    retriever: str  # e.g. "bm25", "dense" — which component produced this score


class GuardrailDecision(BaseModel):
    """Record of a guardrail rail evaluating some input/output."""

    rail: str  # e.g. "input.pii_scan", "retrieval.injection_scan", "output.citation_check"
    passed: bool
    reason: str | None = None
    flagged_spans: list[str] = Field(default_factory=list)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    k: int = Field(default=5, ge=1, le=20)


class QueryResponse(BaseModel):
    trace_id: str
    answer: str
    refused: bool
    citations: list[Citation]
    guardrail_decisions: list[GuardrailDecision]
    latency_ms: float


class EvaluationCase(BaseModel):
    """One row of a versioned evaluation dataset."""

    id: str
    question: str
    gold_document_ids: list[str] = Field(default_factory=list)
    gold_chunk_ids: list[str] = Field(default_factory=list)
    expect_refusal: bool = False
    category: str = "retrieval"  # retrieval | refusal | guardrail
    language: str = "en"
    notes: str | None = None


class EvaluationResult(BaseModel):
    """Aggregate result of running an evaluation dataset against the current system."""

    dataset_id: str
    dataset_version: str
    metric_name: str
    value: float | str  # "TBD" permitted when genuinely not yet measured
    baseline: float | str | None = None
    acceptance_threshold: float | str | None = None
    computed_at: datetime = Field(default_factory=_utcnow)
    limitations: str | None = None
