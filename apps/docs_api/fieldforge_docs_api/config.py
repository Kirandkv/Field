from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv("FIELDFORGE_DB_PATH", "./fieldforge_docs.sqlite3")
    max_upload_bytes: int = int(os.getenv("FIELDFORGE_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
    default_k: int = int(os.getenv("FIELDFORGE_RETRIEVAL_K", "5"))

    # FieldForge Edge (docs/adr/0005-edge-offline-profile.md) — both default to the
    # unmodified slice-1 behavior; opting into either requires Ollama running locally.
    retrieval_mode: str = os.getenv("FIELDFORGE_RETRIEVAL_MODE", "sparse")  # "sparse" | "hybrid"
    answer_mode: str = os.getenv("FIELDFORGE_ANSWER_MODE", "extractive")  # "extractive" | "generative"
    qdrant_path: str = os.getenv("FIELDFORGE_QDRANT_PATH", "./fieldforge_qdrant")
    backup_dir: str = os.getenv("FIELDFORGE_BACKUP_DIR", "./fieldforge_backups")
    ollama_host: str = os.getenv("FIELDFORGE_OLLAMA_HOST", "http://localhost:11434")


settings = Settings()
