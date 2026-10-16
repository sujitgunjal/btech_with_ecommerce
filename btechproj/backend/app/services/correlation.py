"""Deterministic co-occurrence rules for collected telemetry.

A correlation says two observations share a trace or a time window.
It does not assert that one caused the other.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from ..schemas.evidence import NormalizedEvent


def _trace_id(record: Any) -> str | None:
    if isinstance(record, dict) and record.get("trace_id"):
        return str(record["trace_id"])
    metadata = getattr(record, "metadata", None)
    if metadata is None and isinstance(record, dict):
        metadata = record.get("metadata") or {}
    if isinstance(metadata, dict) and metadata.get("trace_id"):
        return str(metadata["trace_id"])
    content = getattr(record, "content", None)
    if content is None and isinstance(record, dict):
        content = record.get("content") or record.get("message") or ""
    if not isinstance(content, str) or not content.startswith("{"):
        return None
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    trace_id = payload.get("trace_id")
    return str(trace_id) if trace_id else None


def _service(record: Any) -> str:
    value = getattr(record, "service", None)
    if value is None and isinstance(record, dict):
        value = record.get("service") or ""
    return str(value or "")


def _content(record: Any) -> str:
    value = getattr(record, "content", None)
    if value is None and isinstance(record, dict):
        value = record.get("content") or record.get("message") or ""
    return str(value or "")


def correlation_notes(records: list[Any]) -> list[dict[str, str]]:
    """Return correlation statements grounded only in the supplied records."""
    notes: list[dict[str, str]] = []
    by_trace: dict[str, set[str]] = defaultdict(set)
    for record in records:
        trace_id = _trace_id(record)
        service = _service(record)
        if trace_id and service:
            by_trace[trace_id].add(service)

    for trace_id, services in sorted(by_trace.items()):
        if len(services) < 2:
            continue
        joined = ", ".join(sorted(services))
        notes.append(
            {
                "relation": "shared_trace",
                "causation": "not_established",
                "content": (
                    f"Trace {trace_id} was observed on {joined}. "
                    "Sharing a trace shows the calls belong to one request. "
                    "It does not by itself identify a cause."
                ),
            }
        )

    shop_errors = [
        record
        for record in records
        if _service(record) == "ecommerce-shop-api" and _looks_like_failure(record)
    ]
    payment_errors = [
        record
        for record in records
        if _service(record) == "ecommerce-payment-gateway" and _looks_like_failure(record)
    ]
    if shop_errors and payment_errors:
        notes.append(
            {
                "relation": "temporal_cooccurrence",
                "causation": "not_established",
                "content": (
                    f"The shop API has {len(shop_errors)} failure signal(s) and the payment "
                    f"gateway has {len(payment_errors)} failure signal(s) in the same window. "
                    "This is co-occurrence, not a demonstrated cause."
                ),
            }
        )
    return notes


def correlation_events(records: list[Any]) -> list[NormalizedEvent]:
    now = datetime.now(timezone.utc)
    events: list[NormalizedEvent] = []
    for note in correlation_notes(records):
        events.append(
            NormalizedEvent(
                timestamp=now,
                source="correlation",
                service="evidence-correlation",
                event_type=note["relation"],
                severity="info",
                content=note["content"],
                metadata={"causation": note["causation"], "relation": note["relation"]},
            )
        )
    return events


def _looks_like_failure(record: Any) -> bool:
    severity = ""
    if isinstance(record, dict):
        severity = str(record.get("severity") or record.get("level") or "")
    else:
        severity = str(getattr(record, "severity", "") or "")
    if severity.lower() in {"error", "critical", "warning"}:
        return True
    if isinstance(record, dict) and str(record.get("status") or "").lower() == "error":
        return True
    text = _content(record).lower()
    return any(token in text for token in ("timeout", "status=error", "http 5", "failed"))
