"""JSON logs for stdout. Trace ids are included; experiment answers are not."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from opentelemetry import trace


class JsonFormatter(logging.Formatter):
    def __init__(self, service_name: str):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        span = trace.get_current_span()
        context = span.get_span_context()
        trace_id = None
        span_id = None
        if context and context.trace_id:
            trace_id = format(context.trace_id, "032x")
            span_id = format(context.span_id, "016x")
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": trace_id,
            "span_id": span_id,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(service_name: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(service_name))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    logging.getLogger("ecommerce").setLevel(logging.INFO)
