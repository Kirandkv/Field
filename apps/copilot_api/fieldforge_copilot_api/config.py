from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv("FIELDFORGE_COPILOT_DB_PATH", "./fieldforge_copilot.sqlite3")
    docs_api_url: str = os.getenv("FIELDFORGE_DOCS_API_URL", "http://localhost:8000")


settings = Settings()
