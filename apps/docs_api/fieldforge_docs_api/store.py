"""SQLite-backed document/page/chunk store.

Slice 1 uses SQLite (stdlib sqlite3, no ORM) rather than PostgreSQL+SQLAlchemy+Alembic —
see ADR 0001. This is a deliberate scope cut for a single-process vertical slice, not an
oversight; the migration to Postgres is a planned M2 item once a real multi-writer
deployment scenario exists to justify it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fieldforge_contracts import Chunk, ChunkingStrategy, Document, DocumentPage, DocumentStatus

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    language TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    page_count INTEGER,
    sha256 TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    error TEXT
);
CREATE TABLE IF NOT EXISTS pages (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    page_number INTEGER NOT NULL,
    text TEXT NOT NULL,
    ocr_confidence REAL
);
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    page_number INTEGER NOT NULL,
    strategy TEXT NOT NULL,
    text TEXT NOT NULL,
    start_offset INTEGER NOT NULL,
    end_offset INTEGER NOT NULL,
    sequence INTEGER NOT NULL
);
"""


class DocumentStore:
    def __init__(self, db_path: str) -> None:
        self._path = db_path
        parent = Path(db_path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def backup_to(self, backup_path: str) -> None:
        """Uses SQLite's online backup API — safe to call while this store's
        connection is open, unlike a raw file copy. See ADR 0005 decision (Edge).
        """
        Path(backup_path).parent.mkdir(parents=True, exist_ok=True)
        dest = sqlite3.connect(backup_path)
        try:
            self._conn.backup(dest)
        finally:
            dest.close()

    def restore_from(self, backup_path: str) -> None:
        """Closes the current connection, restores from a backup file made by
        `backup_to`, and reopens against the original db path.
        """
        if not Path(backup_path).exists():
            raise FileNotFoundError(f"backup file not found: {backup_path}")
        self._conn.close()
        source = sqlite3.connect(backup_path)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        try:
            source.backup(self._conn)
        finally:
            source.close()

    def save_document(self, doc: Document) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO documents "
            "(id, filename, content_type, language, version, status, page_count, "
            "sha256, uploaded_at, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                doc.id,
                doc.filename,
                doc.content_type,
                doc.language,
                doc.version,
                doc.status.value,
                doc.page_count,
                doc.sha256,
                doc.uploaded_at.isoformat(),
                doc.error,
            ),
        )
        self._conn.commit()

    def save_pages(self, pages: list[DocumentPage]) -> None:
        self._conn.executemany(
            "INSERT OR REPLACE INTO pages (id, document_id, page_number, text, ocr_confidence) "
            "VALUES (?, ?, ?, ?, ?)",
            [(p.id, p.document_id, p.page_number, p.text, p.ocr_confidence) for p in pages],
        )
        self._conn.commit()

    def save_chunks(self, chunks: list[Chunk]) -> None:
        self._conn.executemany(
            "INSERT OR REPLACE INTO chunks "
            "(id, document_id, page_number, strategy, text, start_offset, end_offset, sequence) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    c.id,
                    c.document_id,
                    c.page_number,
                    c.strategy.value,
                    c.text,
                    c.start_offset,
                    c.end_offset,
                    c.sequence,
                )
                for c in chunks
            ],
        )
        self._conn.commit()

    def get_document(self, document_id: str) -> Document | None:
        row = self._conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_document(row)

    def list_documents(self) -> list[Document]:
        rows = self._conn.execute("SELECT * FROM documents ORDER BY uploaded_at DESC").fetchall()
        return [self._row_to_document(row) for row in rows]

    def all_chunks(self) -> list[Chunk]:
        rows = self._conn.execute("SELECT * FROM chunks").fetchall()
        return [
            Chunk(
                id=r[0],
                document_id=r[1],
                page_number=r[2],
                strategy=ChunkingStrategy(r[3]),
                text=r[4],
                start_offset=r[5],
                end_offset=r[6],
                sequence=r[7],
            )
            for r in rows
        ]

    def sha256_exists(self, sha256: str) -> Document | None:
        row = self._conn.execute("SELECT * FROM documents WHERE sha256 = ?", (sha256,)).fetchone()
        return self._row_to_document(row) if row else None

    @staticmethod
    def _row_to_document(row: tuple) -> Document:
        return Document(
            id=row[0],
            filename=row[1],
            content_type=row[2],
            language=row[3],
            version=row[4],
            status=DocumentStatus(row[5]),
            page_count=row[6],
            sha256=row[7],
            uploaded_at=row[8],
            error=row[9],
        )
