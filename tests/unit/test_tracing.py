import asyncio

import fieldforge_observability.tracing as tracing_module
from fieldforge_observability import export_span


def test_export_span_noop_when_url_unset(monkeypatch):
    monkeypatch.delenv("FIELDFORGE_OPS_TRACE_URL", raising=False)
    calls = []
    monkeypatch.setattr(tracing_module, "_post_span", lambda url, span: calls.append((url, span)))
    export_span(service="test", trace_id="t1")
    assert calls == []


def test_export_span_schedules_post_when_url_set(monkeypatch):
    monkeypatch.setenv("FIELDFORGE_OPS_TRACE_URL", "http://example.invalid")
    captured = []

    async def fake_post(url, span):
        captured.append((url, span))

    monkeypatch.setattr(tracing_module, "_post_span", fake_post)

    async def run():
        export_span(service="docs_api", trace_id="t2", status_code=200)
        await asyncio.sleep(0)  # let the scheduled task run

    asyncio.run(run())
    assert len(captured) == 1
    url, span = captured[0]
    assert url == "http://example.invalid"
    assert span["service"] == "docs_api"
    assert span["trace_id"] == "t2"
    assert span["status_code"] == 200


def test_export_span_sync_fallback_swallows_unreachable_errors(monkeypatch):
    """No running event loop (e.g. a plain script) — export_span must not raise
    even if the target is unreachable. See ADR 0004 decision 2.
    """
    monkeypatch.setenv("FIELDFORGE_OPS_TRACE_URL", "http://127.0.0.1:1")
    export_span(service="test", trace_id="t3")  # must not raise
