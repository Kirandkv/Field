"""SQLite-backed store for Ops: evaluation runs, quality-gate results, trace spans,
releases, rollback events. Document-store pattern, same convention as
apps/copilot_api/store.py and apps/mesh_commander/store.py.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fieldforge_contracts import EvaluationRun, QualityGateResult, Release, RollbackEvent, TraceSpan

SCHEMA = """
CREATE TABLE IF NOT EXISTS evaluation_runs (
    id TEXT PRIMARY KEY,
    product TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    is_baseline INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    blob TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quality_gate_results (
    id TEXT PRIMARY KEY,
    product TEXT NOT NULL,
    created_at TEXT NOT NULL,
    blob TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trace_spans (
    id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    service TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    blob TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS releases (
    id TEXT PRIMARY KEY,
    product TEXT NOT NULL,
    environment TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    blob TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rollback_events (
    id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    blob TEXT NOT NULL
);
"""


class OpsStore:
    def __init__(self, db_path: str) -> None:
        parent = Path(db_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- evaluation runs ---

    def save_evaluation_run(self, run: EvaluationRun) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO evaluation_runs (id, product, dataset_id, is_baseline, created_at, blob) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                run.id,
                run.product,
                run.dataset_id,
                int(run.is_baseline),
                run.created_at.isoformat(),
                run.model_dump_json(),
            ),
        )
        self._conn.commit()

    def get_evaluation_run(self, run_id: str) -> EvaluationRun | None:
        row = self._conn.execute("SELECT blob FROM evaluation_runs WHERE id = ?", (run_id,)).fetchone()
        return EvaluationRun.model_validate_json(row[0]) if row else None

    def list_evaluation_runs(self, product: str | None = None) -> list[EvaluationRun]:
        if product:
            rows = self._conn.execute(
                "SELECT blob FROM evaluation_runs WHERE product = ? ORDER BY created_at DESC", (product,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT blob FROM evaluation_runs ORDER BY created_at DESC").fetchall()
        return [EvaluationRun.model_validate_json(r[0]) for r in rows]

    def get_baseline(self, product: str, dataset_id: str) -> EvaluationRun | None:
        row = self._conn.execute(
            "SELECT blob FROM evaluation_runs WHERE product = ? AND dataset_id = ? AND is_baseline = 1 "
            "ORDER BY created_at DESC LIMIT 1",
            (product, dataset_id),
        ).fetchone()
        return EvaluationRun.model_validate_json(row[0]) if row else None

    def get_latest(self, product: str, dataset_id: str) -> EvaluationRun | None:
        row = self._conn.execute(
            "SELECT blob FROM evaluation_runs WHERE product = ? AND dataset_id = ? AND is_baseline = 0 "
            "ORDER BY created_at DESC LIMIT 1",
            (product, dataset_id),
        ).fetchone()
        return EvaluationRun.model_validate_json(row[0]) if row else None

    # --- quality gate results ---

    def save_gate_result(self, result: QualityGateResult) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO quality_gate_results (id, product, created_at, blob) VALUES (?, ?, ?, ?)",
            (result.id, result.product, result.created_at.isoformat(), result.model_dump_json()),
        )
        self._conn.commit()

    def list_gate_results(self, product: str | None = None) -> list[QualityGateResult]:
        if product:
            rows = self._conn.execute(
                "SELECT blob FROM quality_gate_results WHERE product = ? ORDER BY created_at DESC", (product,)
            ).fetchall()
        else:
            query = "SELECT blob FROM quality_gate_results ORDER BY created_at DESC"
            rows = self._conn.execute(query).fetchall()
        return [QualityGateResult.model_validate_json(r[0]) for r in rows]

    # --- trace spans ---

    def save_trace_span(self, span: TraceSpan) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO trace_spans (id, trace_id, service, timestamp, blob) "
            "VALUES (?, ?, ?, ?, ?)",
            (span.id, span.trace_id, span.service, span.timestamp.isoformat(), span.model_dump_json()),
        )
        self._conn.commit()

    def list_trace_spans(self, service: str | None = None, limit: int = 200) -> list[TraceSpan]:
        if service:
            query = "SELECT blob FROM trace_spans WHERE service = ? ORDER BY timestamp DESC LIMIT ?"
            rows = self._conn.execute(query, (service, limit)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT blob FROM trace_spans ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [TraceSpan.model_validate_json(r[0]) for r in rows]

    def get_trace(self, trace_id: str) -> list[TraceSpan]:
        rows = self._conn.execute(
            "SELECT blob FROM trace_spans WHERE trace_id = ? ORDER BY timestamp ASC", (trace_id,)
        ).fetchall()
        return [TraceSpan.model_validate_json(r[0]) for r in rows]

    # --- releases ---

    def save_release(self, release: Release) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO releases (id, product, environment, status, created_at, blob) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                release.id,
                release.product,
                release.environment,
                release.status.value,
                release.created_at.isoformat(),
                release.model_dump_json(),
            ),
        )
        self._conn.commit()

    def get_release(self, release_id: str) -> Release | None:
        row = self._conn.execute("SELECT blob FROM releases WHERE id = ?", (release_id,)).fetchone()
        return Release.model_validate_json(row[0]) if row else None

    def list_releases(self, product: str | None = None) -> list[Release]:
        if product:
            rows = self._conn.execute(
                "SELECT blob FROM releases WHERE product = ? ORDER BY created_at DESC", (product,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT blob FROM releases ORDER BY created_at DESC").fetchall()
        return [Release.model_validate_json(r[0]) for r in rows]

    def get_active_release(self, product: str, environment: str) -> Release | None:
        row = self._conn.execute(
            "SELECT blob FROM releases WHERE product = ? AND environment = ? AND status = 'active' "
            "ORDER BY created_at DESC LIMIT 1",
            (product, environment),
        ).fetchone()
        return Release.model_validate_json(row[0]) if row else None

    # --- rollback events ---

    def save_rollback_event(self, event: RollbackEvent) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO rollback_events (id, release_id, created_at, blob) "
            "VALUES (?, ?, ?, ?)",
            (event.id, event.release_id, event.created_at.isoformat(), event.model_dump_json()),
        )
        self._conn.commit()

    def list_rollback_events(self, release_id: str | None = None) -> list[RollbackEvent]:
        if release_id:
            query = "SELECT blob FROM rollback_events WHERE release_id = ? ORDER BY created_at DESC"
            rows = self._conn.execute(query, (release_id,)).fetchall()
        else:
            rows = self._conn.execute("SELECT blob FROM rollback_events ORDER BY created_at DESC").fetchall()
        return [RollbackEvent.model_validate_json(r[0]) for r in rows]
