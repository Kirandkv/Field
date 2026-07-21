from __future__ import annotations

import logging
import time

from fieldforge_observability import new_trace_id
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("fieldforge.ops_api.request")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = new_trace_id()
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request failed",
                extra={"extra_fields": {"trace_id": trace_id, "path": request.url.path}},
            )
            raise
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Trace-Id"] = trace_id
        logger.info(
            "request completed",
            extra={
                "extra_fields": {
                    "trace_id": trace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                }
            },
        )
        return response
