"""Fire-and-forget trace export to FieldForge Ops.

See docs/adr/0004-ops-quality-gate.md decision 2: this must never become a new
availability dependency for the service calling it. If `FIELDFORGE_OPS_TRACE_URL`
is unset (the default), export is a no-op. If it's set but Ops is unreachable, the
failure is swallowed and logged at debug level only — the caller's own request
always succeeds or fails on its own merits, never on Ops' availability.
"""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

logger = logging.getLogger("fieldforge.observability.tracing")

_EXPORT_TIMEOUT_SECONDS = 2.0


def _trace_url() -> str | None:
    return os.getenv("FIELDFORGE_OPS_TRACE_URL")


async def _post_span(url: str, span: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=_EXPORT_TIMEOUT_SECONDS) as client:
            await client.post(f"{url}/traces", json=span)
    except httpx.RequestError as exc:
        logger.debug("trace export failed (non-fatal): %s", exc)


def export_span(service: str, trace_id: str, **fields: object) -> None:
    """Schedules a fire-and-forget export of one span. Safe to call from an async
    request handler/middleware — does not await the network call, so it adds no
    latency to the response it's describing.
    """
    url = _trace_url()
    if not url:
        return
    span = {"service": service, "trace_id": trace_id, **fields}
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_post_span(url, span))
    except RuntimeError:
        # No running event loop (e.g. a sync script) — export synchronously with the
        # same short timeout rather than silently dropping the span.
        try:
            httpx.post(f"{url}/traces", json=span, timeout=_EXPORT_TIMEOUT_SECONDS)
        except httpx.RequestError as exc:
            logger.debug("trace export failed (non-fatal): %s", exc)
