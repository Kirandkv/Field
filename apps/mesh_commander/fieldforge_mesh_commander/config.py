from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv("FIELDFORGE_MESH_COMMANDER_DB_PATH", "./fieldforge_mesh_commander.sqlite3")
    agent_token: str = os.getenv("FIELDFORGE_MESH_AGENT_TOKEN", "dev-mesh-token")
    delegation_timeout_seconds: float = float(os.getenv("FIELDFORGE_MESH_DELEGATION_TIMEOUT_S", "10"))


settings = Settings()
