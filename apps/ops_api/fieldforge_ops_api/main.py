"""FieldForge Ops API — the LLMOps control plane for Docs, Copilot, and Mesh.

Ingests the real evaluation reports those products already produce, enforces a
quality gate against their committed baselines, collects trace spans exported by
their request middleware, and gate-enforces a deployment/rollback registry. See
docs/adr/0004-ops-quality-gate.md.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fieldforge_contracts import (
    EvaluationRun,
    GateDecision,
    QualityGateResult,
    Release,
    ReleaseStatus,
    RollbackEvent,
    TraceSpan,
)
from fieldforge_observability import configure_json_logging
from pydantic import BaseModel

from fieldforge_ops_api.config import settings
from fieldforge_ops_api.gate import compute_gate
from fieldforge_ops_api.middleware import CorrelationIdMiddleware
from fieldforge_ops_api.store import OpsStore

configure_json_logging()
logger = logging.getLogger("fieldforge.ops_api")

app = FastAPI(
    title="FieldForge Ops API",
    version="0.1.0",
    description="Evaluation registry, quality gate, trace explorer, and deployment registry.",
)
app.add_middleware(CorrelationIdMiddleware)

store = OpsStore(settings.db_path)


@app.on_event("shutdown")
def _shutdown() -> None:
    store.close()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "evaluation_runs": len(store.list_evaluation_runs()),
        "gate_results": len(store.list_gate_results()),
        "trace_spans": len(store.list_trace_spans(limit=10_000)),
        "releases": len(store.list_releases()),
    }


# --- evaluation registry ---


class EvaluationRunCreate(BaseModel):
    product: str
    dataset_id: str
    dataset_version: str
    case_count: int
    metrics: dict[str, float | str]
    is_baseline: bool = False
    source: str


@app.post("/evaluations", status_code=201)
def ingest_evaluation_run(body: EvaluationRunCreate) -> EvaluationRun:
    run = EvaluationRun(**body.model_dump())
    store.save_evaluation_run(run)
    logger.info(
        "evaluation run ingested",
        extra={
            "extra_fields": {
                "product": run.product,
                "dataset_id": run.dataset_id,
                "is_baseline": run.is_baseline,
            }
        },
    )
    return run


@app.get("/evaluations")
def list_evaluation_runs(product: str | None = None) -> list[EvaluationRun]:
    return store.list_evaluation_runs(product)


@app.get("/evaluations/{run_id}")
def get_evaluation_run(run_id: str) -> EvaluationRun:
    run = store.get_evaluation_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"evaluation run {run_id} not found")
    return run


# --- quality gate ---


class QualityGateRequest(BaseModel):
    product: str
    dataset_id: str


@app.post("/quality-gate/run", status_code=201)
def run_quality_gate(body: QualityGateRequest) -> QualityGateResult:
    latest = store.get_latest(body.product, body.dataset_id)
    if latest is None:
        raise HTTPException(
            status_code=404,
            detail=f"no evaluation run found for product={body.product!r} dataset_id={body.dataset_id!r}",
        )
    baseline = store.get_baseline(body.product, body.dataset_id)
    result = compute_gate(latest, baseline)
    store.save_gate_result(result)
    logger.info(
        "quality gate evaluated",
        extra={
            "extra_fields": {
                "product": result.product,
                "dataset_id": result.dataset_id,
                "decision": result.decision.value,
            }
        },
    )
    return result


@app.get("/quality-gate")
def list_gate_results(product: str | None = None) -> list[QualityGateResult]:
    return store.list_gate_results(product)


# --- trace explorer ---


class TraceSpanCreate(BaseModel):
    service: str
    trace_id: str
    method: str | None = None
    path: str | None = None
    status_code: int | None = None
    duration_ms: float | None = None
    level: str = "INFO"
    message: str = ""


@app.post("/traces", status_code=201)
def ingest_trace_span(body: TraceSpanCreate) -> TraceSpan:
    span = TraceSpan(**body.model_dump())
    store.save_trace_span(span)
    return span


@app.get("/traces")
def list_trace_spans(service: str | None = None, limit: int = 200) -> list[TraceSpan]:
    return store.list_trace_spans(service, limit)


@app.get("/traces/{trace_id}")
def get_trace(trace_id: str) -> list[TraceSpan]:
    spans = store.get_trace(trace_id)
    if not spans:
        raise HTTPException(status_code=404, detail=f"no spans found for trace {trace_id}")
    return spans


# --- deployment registry (bookkeeping only — see ADR 0004 decision 3) ---


class DeploymentCreate(BaseModel):
    product: str
    environment: str
    version_label: str
    evaluation_run_id: str


@app.post("/deployments", status_code=201)
def create_deployment(body: DeploymentCreate) -> Release:
    run = store.get_evaluation_run(body.evaluation_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"evaluation run {body.evaluation_run_id} not found")

    all_gate_results = store.list_gate_results(body.product)
    gate_results = [r for r in all_gate_results if r.evaluation_run_id == body.evaluation_run_id]
    if not gate_results:
        raise HTTPException(
            status_code=409,
            detail=(
                f"evaluation run {body.evaluation_run_id} has not passed a quality gate "
                f"— run POST /quality-gate/run first"
            ),
        )
    latest_gate = gate_results[0]
    if latest_gate.decision != GateDecision.PASS:
        raise HTTPException(
            status_code=409,
            detail=(
                f"evaluation run {body.evaluation_run_id}'s quality gate decision is "
                f"{latest_gate.decision.value!r}, not 'pass' — deployment blocked"
            ),
        )

    release = Release(**body.model_dump())
    store.save_release(release)
    logger.info(
        "release created",
        extra={
            "extra_fields": {
                "release_id": release.id,
                "product": release.product,
                "environment": release.environment,
                "version_label": release.version_label,
            }
        },
    )
    return release


@app.get("/deployments")
def list_deployments(product: str | None = None) -> list[Release]:
    return store.list_releases(product)


@app.get("/deployments/{release_id}")
def get_deployment(release_id: str) -> Release:
    release = store.get_release(release_id)
    if release is None:
        raise HTTPException(status_code=404, detail=f"release {release_id} not found")
    return release


class RollbackRequest(BaseModel):
    reason: str
    triggered_by: str


@app.post("/deployments/{release_id}/rollback")
def rollback_deployment(release_id: str, body: RollbackRequest) -> Release:
    release = store.get_release(release_id)
    if release is None:
        raise HTTPException(status_code=404, detail=f"release {release_id} not found")
    if release.status == ReleaseStatus.ROLLED_BACK:
        raise HTTPException(status_code=409, detail=f"release {release_id} is already rolled back")

    previous = _previous_release(release)
    event = RollbackEvent(
        release_id=release.id,
        previous_active_release_id=previous.id if previous else None,
        reason=body.reason,
        triggered_by=body.triggered_by,
    )
    store.save_rollback_event(event)

    release = release.model_copy(update={"status": ReleaseStatus.ROLLED_BACK})
    store.save_release(release)

    logger.info(
        "release rolled back",
        extra={
            "extra_fields": {
                "release_id": release.id,
                "reason": body.reason,
                "triggered_by": body.triggered_by,
            }
        },
    )
    return release


def _previous_release(release: Release) -> Release | None:
    siblings = [
        r
        for r in store.list_releases(release.product)
        if r.environment == release.environment and r.id != release.id and r.created_at < release.created_at
    ]
    return siblings[0] if siblings else None


@app.get("/deployments/{release_id}/rollback-events")
def list_rollback_events(release_id: str) -> list[RollbackEvent]:
    return store.list_rollback_events(release_id)
