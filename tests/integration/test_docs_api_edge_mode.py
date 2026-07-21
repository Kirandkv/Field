"""FieldForge Edge mode tests for apps/docs_api.

The degradation tests (hybrid mode requested but Ollama unreachable) run
everywhere, since that's the exact path CI takes with no Ollama installed. The
real-hybrid-retrieval test is skipped when Ollama isn't reachable — see
tests/unit/test_ollama_adapters.py for the shared skip logic.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient


def _ollama_reachable() -> bool:
    try:
        return httpx.get("http://localhost:11434/api/tags", timeout=1.0).status_code == 200
    except httpx.RequestError:
        return False


requires_ollama = pytest.mark.skipif(not _ollama_reachable(), reason="Ollama not reachable on this machine")


def _fresh_client(monkeypatch, tmp_path, env: dict[str, str]):
    monkeypatch.setenv("FIELDFORGE_DB_PATH", str(tmp_path / "edge_test.sqlite3"))
    monkeypatch.setenv("FIELDFORGE_QDRANT_PATH", str(tmp_path / "edge_qdrant"))
    monkeypatch.setenv("FIELDFORGE_BACKUP_DIR", str(tmp_path / "edge_backups"))
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    from fieldforge_docs_api import config as config_module

    importlib.reload(config_module)
    from fieldforge_docs_api import main as main_module

    importlib.reload(main_module)
    return main_module


def test_default_mode_unchanged(monkeypatch, tmp_path):
    """Slice-1 default (no Edge env vars set) behaves exactly as before."""
    main_module = _fresh_client(monkeypatch, tmp_path, {})
    with TestClient(main_module.app) as client:
        health = client.get("/health").json()
        assert health["retrieval_mode"] == "sparse"
        assert health["answer_mode"] == "extractive"
        assert health["dense_available"] is False
    main_module.store.close()


def test_hybrid_mode_degrades_gracefully_when_ollama_unreachable(monkeypatch, tmp_path):
    main_module = _fresh_client(
        monkeypatch,
        tmp_path,
        {
            "FIELDFORGE_RETRIEVAL_MODE": "hybrid",
            "FIELDFORGE_OLLAMA_HOST": "http://127.0.0.1:1",
        },
    )
    with TestClient(main_module.app) as client:
        health = client.get("/health").json()
        assert health["retrieval_mode"] == "hybrid"
        assert health["dense_available"] is False  # degraded, not crashed

        upload = client.post(
            "/documents", files={"file": ("a.txt", b"calibration interval is ninety days", "text/plain")}
        )
        assert upload.status_code == 201

        resp = client.post("/query", json={"question": "calibration interval"})
        assert resp.status_code == 200
        assert resp.json()["refused"] is False  # sparse retrieval still works
    main_module.store.close()
    if main_module.dense_index is not None:
        main_module.dense_index.close()


def test_edge_resources_endpoint_works_without_ollama(monkeypatch, tmp_path):
    main_module = _fresh_client(monkeypatch, tmp_path, {"FIELDFORGE_OLLAMA_HOST": "http://127.0.0.1:1"})
    with TestClient(main_module.app) as client:
        resp = client.get("/edge/resources")
        assert resp.status_code == 200
        body = resp.json()
        assert body["process_rss_mb"] > 0
        assert body["ollama"]["reachable"] is False
    main_module.store.close()


def test_backup_and_restore_round_trip(monkeypatch, tmp_path):
    main_module = _fresh_client(monkeypatch, tmp_path, {})
    with TestClient(main_module.app) as client:
        client.post("/documents", files={"file": ("a.txt", b"some content here", "text/plain")})
        assert len(client.get("/documents").json()) == 1

        backup = client.post("/edge/backup")
        assert backup.status_code == 201
        backup_path = backup.json()["backup_path"]

        client.post("/documents", files={"file": ("b.txt", b"more content here too", "text/plain")})
        assert len(client.get("/documents").json()) == 2

        restore = client.post("/edge/restore", json={"backup_path": backup_path})
        assert restore.status_code == 200
        assert len(client.get("/documents").json()) == 1  # back to the pre-second-upload state
    main_module.store.close()


def test_restore_unknown_backup_inside_backup_dir_404s(monkeypatch, tmp_path):
    main_module = _fresh_client(monkeypatch, tmp_path, {})
    with TestClient(main_module.app) as client:
        missing = str(tmp_path / "edge_backups" / "does-not-exist.sqlite3")
        resp = client.post("/edge/restore", json={"backup_path": missing})
        assert resp.status_code == 404
    main_module.store.close()


def test_restore_path_outside_backup_dir_is_rejected(monkeypatch, tmp_path):
    """A restore path outside the configured backup directory must be refused, not
    used to overwrite the live database from an arbitrary file. See
    docs/threat-model/THREAT_MODEL.md.
    """
    main_module = _fresh_client(monkeypatch, tmp_path, {})
    with TestClient(main_module.app) as client:
        outside_path = str(tmp_path / "not_a_backup.sqlite3")
        Path(outside_path).write_bytes(b"not a real sqlite file")
        resp = client.post("/edge/restore", json={"backup_path": outside_path})
        assert resp.status_code == 400
    main_module.store.close()


@requires_ollama
def test_hybrid_mode_real_dense_retrieval(monkeypatch, tmp_path):
    main_module = _fresh_client(monkeypatch, tmp_path, {"FIELDFORGE_RETRIEVAL_MODE": "hybrid"})
    with TestClient(main_module.app) as client:
        health = client.get("/health").json()
        assert health["dense_available"] is True

        client.post(
            "/documents",
            files={
                "file": (
                    "manual.txt",
                    b"The methane sensor calibration interval is ninety days for FF-R07.",
                    "text/plain",
                )
            },
        )
        resp = client.post("/query", json={"question": "sensor calibration interval"})
        assert resp.status_code == 200
        assert resp.json()["refused"] is False
    main_module.store.close()
    if main_module.dense_index is not None:
        main_module.dense_index.close()
