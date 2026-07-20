"""SQLite-backed store for Copilot's own records: incidents, approval requests/
decisions, maintenance tickets. Document-store pattern (one JSON blob per row) rather
than a flat relational schema — these are nested Pydantic models and slice 1 has no
need for SQL-level querying across their internals. See ADR 0001 for why SQLite
(not Postgres) is the slice-level default across this suite.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fieldforge_contracts import ApprovalDecision, ApprovalRequest, Incident, MaintenanceTicket

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    blob TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approval_requests (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    decided INTEGER NOT NULL DEFAULT 0,
    blob TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approval_decisions (
    id TEXT PRIMARY KEY,
    approval_request_id TEXT NOT NULL,
    blob TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS maintenance_tickets (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    blob TEXT NOT NULL
);
"""


class CopilotStore:
    def __init__(self, db_path: str) -> None:
        parent = Path(db_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def save_incident(self, incident: Incident) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO incidents (id, state, updated_at, blob) VALUES (?, ?, ?, ?)",
            (incident.id, incident.state.value, incident.updated_at.isoformat(), incident.model_dump_json()),
        )
        self._conn.commit()

    def get_incident(self, incident_id: str) -> Incident | None:
        row = self._conn.execute("SELECT blob FROM incidents WHERE id = ?", (incident_id,)).fetchone()
        return Incident.model_validate_json(row[0]) if row else None

    def list_incidents(self) -> list[Incident]:
        rows = self._conn.execute("SELECT blob FROM incidents ORDER BY updated_at DESC").fetchall()
        return [Incident.model_validate_json(r[0]) for r in rows]

    def save_approval_request(self, approval: ApprovalRequest) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO approval_requests (id, incident_id, decided, blob) VALUES (?, ?, ?, ?)",
            (approval.id, approval.incident_id, int(approval.decided), approval.model_dump_json()),
        )
        self._conn.commit()

    def get_approval_request(self, approval_id: str) -> ApprovalRequest | None:
        row = self._conn.execute(
            "SELECT blob FROM approval_requests WHERE id = ?", (approval_id,)
        ).fetchone()
        return ApprovalRequest.model_validate_json(row[0]) if row else None

    def list_pending_approvals(self) -> list[ApprovalRequest]:
        rows = self._conn.execute("SELECT blob FROM approval_requests WHERE decided = 0").fetchall()
        return [ApprovalRequest.model_validate_json(r[0]) for r in rows]

    def save_approval_decision(self, decision: ApprovalDecision) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO approval_decisions (id, approval_request_id, blob) VALUES (?, ?, ?)",
            (decision.id, decision.approval_request_id, decision.model_dump_json()),
        )
        self._conn.commit()

    def save_ticket(self, ticket: MaintenanceTicket) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO maintenance_tickets (id, incident_id, blob) VALUES (?, ?, ?)",
            (ticket.id, ticket.incident_id, ticket.model_dump_json()),
        )
        self._conn.commit()

    def list_tickets(self) -> list[MaintenanceTicket]:
        rows = self._conn.execute("SELECT blob FROM maintenance_tickets").fetchall()
        return [MaintenanceTicket.model_validate_json(r[0]) for r in rows]
