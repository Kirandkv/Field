from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv("FIELDFORGE_DB_PATH", "./fieldforge_docs.sqlite3")
    max_upload_bytes: int = int(os.getenv("FIELDFORGE_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
    default_k: int = int(os.getenv("FIELDFORGE_RETRIEVAL_K", "5"))


settings = Settings()
