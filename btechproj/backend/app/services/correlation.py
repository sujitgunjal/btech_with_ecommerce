"""Deterministic co-occurrence rules for collected telemetry.

A correlation says two observations share a trace, an endpoint, a service
relationship, or a nearby timestamp. It does not assert that one caused the other.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from ..schemas.evidence import NormalizedEvent

DEFAULT_TOLERANCE_SECONDS = 30.0
MAX_NEW_CORRELATIONS = 25

RELATED_SERVICES = {
    "postgres": {"user-service", "product-service", "order-service"},
    "product-service": {"order-service", "user-service"},
    "order-service": {"product-service", "user-service"},
    "user-service": {"postgres"},
    "ecommerce-shop-api": {"ecommerce-payment-gateway"},
    "ecommerce-payment-gateway": {"ecommerce-shop-api"},
}

_ENDPOINT_RE = re.compile(
    r"\b(?:GET|POST|PUT|PATCH|DELETE|HEAD)\s+(/[A-Za-z0-9_./{}-]*)",
    re.IGNORECASE,
)
_PATH_RE = re.compile(r"path=([/A-Za-z0-9_./{}-]*)", re.IGNORECASE)
_METRIC_RELEVANT = (
    "latency",
    "error",
    "duration",
    "timeout",
    "cpu",
    "memory",
)


def correlation_notes(
    records: list[Any],
    tolerance_seconds: float = DEFAULT_TOLERANCE_SECONDS,
) -> list[dict[str, Any]]:
    """Return correlation statements grounded only in the supplied records."""
    notes: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, tuple[str, ...]]] = set()
    indexed = [_view(record, index) for index, record in enumerate(records or [])]

    by_trace: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in indexed:
        if item["trace_id"] and item["service"]:
            by_trace[item["trace_id"]].append(item)

    for trace_id, items in sorted(by_trace.items()):
        services = {item["service"] for item in items}
        if len(services) < 2:
            continue
        joined = ", ".join(sorted(services))
        notes.append(
            _note(
                relation="shared_trace",
                method="trace_id",
                items=items,
                content=(
                    f"Trace {trace_id} was observed on {joined}. "
                    "Sharing a trace shows the calls belong to one request. "
                    "It does not by itself identify a cause."
                ),
            )
        )
        seen_pairs.add(("trace_id", tuple(sorted(item["ref"] for item in items))))

    shop_errors = [
        item for item in indexed
        if item["service"] == "ecommerce-shop-api" and item["failure"]
    ]
    payment_errors = [
        item for item in indexed
        if item["service"] == "ecommerce-payment-gateway" and item["failure"]
    ]
    if shop_errors and payment_errors:
        combined = shop_errors + payment_errors
        notes.append(
            _note(
                relation="temporal_cooccurrence",
                method="time_window",
                items=combined,
                content=(
                    f"The shop API has {len(shop_errors)} failure signal(s) and the payment "
                    f"gateway has {len(payment_errors)} failure signal(s) in the same window. "
                    "This is co-occurrence, not a demonstrated cause."
                ),
            )
        )

    added = 0
    for left, right, method, relation, explanation in _candidate_pairs(indexed, tolerance_seconds):
        if added >= MAX_NEW_CORRELATIONS:
            break
        pair_key = (method, tuple(sorted((left["ref"], right["ref"]))))
        if pair_key in seen_pairs:
            continue
        if method != "trace_id" and _already_traced(left, right, seen_pairs):
            continue
        seen_pairs.add(pair_key)
        notes.append(
            _note(
                relation=relation,
                method=method,
                items=[left, right],
                content=explanation,
            )
        )
        added += 1
    return notes


def correlation_events(
    records: list[Any],
    tolerance_seconds: float = DEFAULT_TOLERANCE_SECONDS,
) -> list[NormalizedEvent]:
    now = datetime.now(timezone.utc)
    events: list[NormalizedEvent] = []
    for note in correlation_notes(records, tolerance_seconds=tolerance_seconds):
        events.append(
            NormalizedEvent(
                timestamp=now,
                source="correlation",
                service="evidence-correlation",
                event_type=note["relation"],
                severity="info",
                content=note["content"],
                metadata={
                    "causation": note["causation"],
                    "relation": note["relation"],
                    "matching_method": note["matching_method"],
                    "time_difference_seconds": note["time_difference_seconds"],
                    "timestamps": note["timestamps"],
                    "services": note["services"],
                    "sources": note["sources"],
                    "evidence_refs": note["evidence_refs"],
                },
            )
        )
    return events


def _candidate_pairs(items: list[dict[str, Any]], tolerance_seconds: float):
    logs = [item for item in items if item["kind"] == "log"]
    spans = [item for item in items if item["kind"] == "trace"]
    metrics = [item for item in items if item["kind"] == "metric" and item["relevant_metric"]]
    anchors = [item for item in items if item["kind"] == "deployment"]

    for log in logs:
        for span in spans:
            if not log["trace_id"] or log["trace_id"] != span["trace_id"]:
                continue
            yield (
                log,
                span,
                "trace_id",
                "trace_request",
                (
                    f"Log and span share trace {log['trace_id']}. "
                    "They belong to the same request. This does not identify a cause."
                ),
            )

    for log in logs:
        if not log["endpoint"]:
            continue
        for span in spans:
            if log["endpoint"] != span["endpoint"]:
                continue
            if not _related(log["service"], span["service"]):
                continue
            if log["trace_id"] and log["trace_id"] == span["trace_id"]:
                continue
            if not _time_compatible(log, span, tolerance_seconds):
                continue
            yield (
                log,
                span,
                "endpoint",
                "endpoint",
                (
                    f"Log and span both refer to {log['endpoint']}. "
                    "The link is the endpoint name"
                    f"{_time_phrase(log, span)}. "
                    "It is not proof of causation."
                ),
            )

    for log in logs:
        if not log["failure"]:
            continue
        for metric in metrics:
            if not _related(log["service"], metric["service"]):
                continue
            if not _within(log, metric, tolerance_seconds):
                continue
            yield (
                log,
                metric,
                "time_window",
                "timestamp",
                (
                    "A failure log and a latency or error metric are inside the matching tolerance "
                    f"for {log['service'] or metric['service']}"
                    f"{_time_phrase(log, metric)}. "
                    "Proximity in time is not proof of causation."
                ),
            )

    for anchor in anchors:
        for other in logs + metrics + spans:
            if other is anchor or not _related(anchor["service"], other["service"]):
                continue
            if not other["failure"] and other["kind"] != "metric":
                continue
            if not _within(anchor, other, tolerance_seconds):
                continue
            yield (
                anchor,
                other,
                "time_window",
                "service",
                (
                    "A deployment or fault record and a service signal fall inside the matching "
                    f"tolerance{_time_phrase(anchor, other)}. "
                    "Sharing a window does not show that the deployment or fault caused the signal."
                ),
            )


def _note(relation: str, method: str, items: list[dict[str, Any]], content: str) -> dict[str, Any]:
    timestamps = [item["timestamp_text"] for item in items if item["timestamp_text"]]
    return {
        "relation": relation,
        "causation": "not_established",
        "matching_method": method,
        "time_difference_seconds": _span_seconds(items),
        "timestamps": timestamps,
        "services": sorted({item["service"] for item in items if item["service"]}),
        "sources": sorted({item["source"] for item in items if item["source"]}),
        "evidence_refs": [item["ref"] for item in items],
        "content": content,
    }


def _view(record: Any, index: int) -> dict[str, Any]:
    source = _text(record, "source").lower()
    event_type = _text(record, "event_type").lower()
    content = _content(record)
    kind = _kind(source, event_type, content)
    moment = _timestamp(record)
    return {
        "ref": f"{source or 'record'}:{index}",
        "source": source,
        "service": _service(record),
        "kind": kind,
        "failure": _looks_like_failure(record),
        "trace_id": _trace_id(record),
        "endpoint": _endpoint(record, content),
        "timestamp": moment,
        "timestamp_text": moment.isoformat() if moment else "",
        "relevant_metric": _relevant_metric(event_type, content),
        "content": content,
    }


def _kind(source: str, event_type: str, content: str) -> str:
    if source in {"deployment", "git"} or "deploy" in event_type or "fault" in event_type:
        return "deployment"
    if source == "loki" or event_type == "log_entry":
        return "log"
    if source == "prometheus":
        return "metric"
    if source == "jaeger" or event_type == "trace":
        return "trace"
    lowered = content.lower()
    if "span " in lowered:
        return "trace"
    return "other"


def _relevant_metric(event_type: str, content: str) -> bool:
    text = f"{event_type} {content}".lower()
    return any(token in text for token in _METRIC_RELEVANT)


def _related(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    return right in RELATED_SERVICES.get(left, set()) or left in RELATED_SERVICES.get(right, set())


def _time_compatible(left: dict[str, Any], right: dict[str, Any], tolerance_seconds: float) -> bool:
    if left["timestamp"] is None or right["timestamp"] is None:
        return True
    return _within(left, right, tolerance_seconds)


def _within(left: dict[str, Any], right: dict[str, Any], tolerance_seconds: float) -> bool:
    if left["timestamp"] is None or right["timestamp"] is None:
        return False
    return abs((left["timestamp"] - right["timestamp"]).total_seconds()) <= tolerance_seconds


def _span_seconds(items: list[dict[str, Any]]) -> float | None:
    moments = [item["timestamp"] for item in items if item["timestamp"] is not None]
    if len(moments) < 2:
        return None
    return round(abs((max(moments) - min(moments)).total_seconds()), 3)


def _time_phrase(left: dict[str, Any], right: dict[str, Any]) -> str:
    gap = _span_seconds([left, right])
    if gap is None:
        return ""
    return f", {gap}s apart"


def _already_traced(left: dict[str, Any], right: dict[str, Any], seen_pairs: set[tuple[str, tuple[str, ...]]]) -> bool:
    if not left["trace_id"] or left["trace_id"] != right["trace_id"]:
        return False
    return any(key[0] == "trace_id" and left["ref"] in key[1] and right["ref"] in key[1] for key in seen_pairs)


def _trace_id(record: Any) -> str | None:
    if isinstance(record, dict) and record.get("trace_id"):
        return str(record["trace_id"])
    metadata = getattr(record, "metadata", None)
    if metadata is None and isinstance(record, dict):
        metadata = record.get("metadata") or {}
    if isinstance(metadata, dict) and metadata.get("trace_id"):
        return str(metadata["trace_id"])
    content = _content(record)
    if not content.startswith("{"):
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


def _text(record: Any, field: str) -> str:
    if isinstance(record, dict):
        return str(record.get(field) or "")
    return str(getattr(record, field, "") or "")


def _timestamp(record: Any) -> datetime | None:
    value = record.get("timestamp") if isinstance(record, dict) else getattr(record, "timestamp", None)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _endpoint(record: Any, content: str) -> str:
    candidates = []
    if isinstance(record, dict):
        candidates.extend(
            str(record.get(key) or "")
            for key in ("endpoint", "operation", "path")
        )
        metadata = record.get("metadata") or {}
        if isinstance(metadata, dict):
            candidates.append(str(metadata.get("operation") or ""))
    else:
        metadata = getattr(record, "metadata", None) or {}
        if isinstance(metadata, dict):
            candidates.append(str(metadata.get("operation") or ""))
    candidates.append(content)
    for candidate in candidates:
        path = _path_from_text(candidate)
        if path:
            return path
    return ""


def _path_from_text(value: str) -> str:
    if not value:
        return ""
    match = _PATH_RE.search(value) or _ENDPOINT_RE.search(value)
    if not match:
        if value.startswith("/") and " " not in value:
            path = value
        else:
            return ""
    else:
        path = match.group(1)
    path = path.split("?")[0].rstrip("/") or "/"
    return path.lower()


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
