"""FieldForge Edge support: resource monitoring for the local offline deployment
profile. Backup/restore live on DocumentStore (store.py) since they operate
directly on the SQLite connection. See docs/adr/0005-edge-offline-profile.md.
"""

from __future__ import annotations

import httpx
import psutil


def get_resource_snapshot(ollama_host: str) -> dict:
    process = psutil.Process()
    mem = process.memory_info()
    snapshot: dict = {
        "process_rss_mb": round(mem.rss / (1024 * 1024), 2),
        "process_cpu_percent": process.cpu_percent(interval=0.1),
        "system_cpu_count": psutil.cpu_count(logical=True),
        "system_memory_available_mb": round(psutil.virtual_memory().available / (1024 * 1024), 2),
        "ollama": {"reachable": False, "loaded_models": []},
    }
    try:
        resp = httpx.get(f"{ollama_host}/api/ps", timeout=2.0)
        if resp.status_code == 200:
            snapshot["ollama"]["reachable"] = True
            snapshot["ollama"]["loaded_models"] = [
                {"name": m["name"], "size_mb": round(m.get("size", 0) / (1024 * 1024), 2)}
                for m in resp.json().get("models", [])
            ]
    except httpx.RequestError:
        pass
    return snapshot
