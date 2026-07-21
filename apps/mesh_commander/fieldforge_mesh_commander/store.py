from __future__ import annotations

import sqlite3
from pathlib import Path

from fieldforge_contracts import MeshIncidentReport

SCHEMA = """
CREATE TABLE IF NOT EXISTS mesh_incidents (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    blob TEXT NOT NULL
);
"""


class MeshIncidentStore:
    def __init__(self, db_path: str) -> None:
        parent = Path(db_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def save(self, report: MeshIncidentReport) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO mesh_incidents (id, created_at, blob) VALUES (?, ?, ?)",
            (report.id, report.created_at.isoformat(), report.model_dump_json()),
        )
        self._conn.commit()

    def get(self, report_id: str) -> MeshIncidentReport | None:
        row = self._conn.execute(
            "SELECT blob FROM mesh_incidents WHERE id = ?", (report_id,)
        ).fetchone()
        return MeshIncidentReport.model_validate_json(row[0]) if row else None

    def list(self) -> list[MeshIncidentReport]:
        rows = self._conn.execute("SELECT blob FROM mesh_incidents ORDER BY created_at DESC").fetchall()
        return [MeshIncidentReport.model_validate_json(r[0]) for r in rows]
