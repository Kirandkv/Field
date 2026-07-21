from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv("FIELDFORGE_OPS_DB_PATH", "./fieldforge_ops.sqlite3")


settings = Settings()
