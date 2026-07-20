"""Structured JSON logging + request correlation IDs.

This is slice 1's observability layer: every log line is JSON with a trace_id, so logs
are already machine-parseable and joinable to a specific request. Full OpenTelemetry
distributed tracing (spans across guardrail/retrieval/generation steps, exported to a
collector) is planned for M2 — see docs/ROADMAP.md — once there's a second service to
trace across. A single-process API doesn't yet justify a tracing backend; it does
justify structured logs with a correlation id, which this provides today.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

_trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


def new_trace_id() -> str:
    trace_id = uuid.uuid4().hex
    _trace_id_var.set(trace_id)
    return trace_id


def get_correlation_id() -> str | None:
    return _trace_id_var.get()


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": get_correlation_id(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload)


def configure_json_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
