from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # Static shared-secret, dev-friendly service-to-service auth — see
    # docs/adr/0003-mesh-agent-protocol.md decision 7. Not for production use.
    agent_token: str = os.getenv("FIELDFORGE_MESH_AGENT_TOKEN", "dev-mesh-token")
    self_endpoint: str = os.getenv(
        "FIELDFORGE_TELEMETRY_AGENT_URL", "http://localhost:8021"
    )


settings = Settings()
