"""Evidence preprocessing and formatting for RAG and LLM prompts."""

import logging
from typing import Any

logger = logging.getLogger("incident-backend")

MAX_LOG_ENTRIES = 30
MAX_METRIC_ENTRIES = 20
MAX_TRACE_ENTRIES = 15

#Take database evidence records and convert them into organized text summaries for the LLM.
def format_evidence_for_llm(evidence_rows: list) -> dict[str, str]:
    """Convert stored Evidence ORM rows into grouped text summaries.

    Groups evidence by source (loki/prometheus/jaeger) and formats each
    group into a human-readable text block suitable for an LLM prompt.

    Returns a dict with keys: logs_summary, metrics_summary, traces_summary,
    evidence_stats, and evidence_text (combined).
    """
    logs: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    correlations: list[dict[str, Any]] = []

    for row in evidence_rows:
        entry = {
            "timestamp": str(row.timestamp) if row.timestamp else "",
            "service": row.service or "",
            "event_type": row.event_type,
            "severity": row.severity,
            "content": row.content,
            "metadata": row.metadata_ or {},
        }
        source = (row.source or "").lower()
        if source == "loki":
            logs.append(entry)
        elif source == "prometheus":
            metrics.append(entry)
        elif source == "jaeger":
            traces.append(entry)
        elif source == "correlation":
            correlations.append(entry)
        else:
            logs.append(entry)

    logs_summary = _format_logs(logs)
    metrics_summary = _format_metrics(metrics)
    traces_summary = _format_traces(traces)
    correlation_summary = _format_correlations(correlations)

    stats = (
        f"Evidence collected: {len(logs)} log entries, "
        f"{len(metrics)} metric data points, {len(traces)} trace spans"
    )

    combined = []
    if logs_summary:
        combined.append(f"### Logs\n{logs_summary}")
    if metrics_summary:
        combined.append(f"### Metrics\n{metrics_summary}")
    if traces_summary:
        combined.append(f"### Traces\n{traces_summary}")
    if correlation_summary:
        combined.append(f"### Correlations\n{correlation_summary}")

    return {
        "logs_summary": logs_summary or "No log evidence collected.",
        "metrics_summary": metrics_summary or "No metric evidence collected.",
        "traces_summary": traces_summary or "No trace evidence collected.",
        "evidence_stats": stats,
        "evidence_text": "\n\n".join(combined) if combined else "No evidence was collected from any observability source.",
    }


def _format_correlations(correlations: list[dict[str, Any]]) -> str:
    if not correlations:
        return ""
    return "\n".join(
        f"- {item['content']} Causation is not established."
        for item in correlations[:10]
    )


def _format_logs(logs: list[dict[str, Any]]) -> str:
    """Format log evidence entries into readable text."""
    if not logs:
        return ""

    error_logs = [l for l in logs if l["severity"] in ("error", "critical")]
    warning_logs = [l for l in logs if l["severity"] == "warning"]
    info_logs = [l for l in logs if l["severity"] == "info"]

    lines = []

    if error_logs:
        lines.append(f"Error/Critical logs ({len(error_logs)} entries):")
        for entry in error_logs[:MAX_LOG_ENTRIES]:
            ts = entry["timestamp"]
            svc = entry["service"]
            lines.append(f"  [{ts}] [{svc}] {entry['content']}")

    if warning_logs:
        lines.append(f"Warning logs ({len(warning_logs)} entries):")
        for entry in warning_logs[:MAX_LOG_ENTRIES // 2]:
            ts = entry["timestamp"]
            svc = entry["service"]
            lines.append(f"  [{ts}] [{svc}] {entry['content']}")

    if info_logs:
        lines.append(f"Info logs ({len(info_logs)} entries):")
        for entry in info_logs[:MAX_LOG_ENTRIES // 3]:
            ts = entry["timestamp"]
            svc = entry["service"]
            lines.append(f"  [{ts}] [{svc}] {entry['content']}")

    return "\n".join(lines)


METRIC_PRIORITY = (
    "cpu_usage",
    "memory_usage",
    "error_rate",
    "latency",
    "request_latency",
    "request_rate",
)


def _metric_value(entry: dict[str, Any]) -> float | None:
    value = (entry.get("metadata") or {}).get("value")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _format_metrics(metrics: list[dict[str, Any]]) -> str:
    """Summarize metrics by signal, leading with resource and error peaks.

    A raw dump of the earliest samples is mostly healthy request-rate points.
    CPU, memory, and error peaks are the evidence an investigation needs.
    """
    if not metrics:
        return ""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in metrics:
        grouped.setdefault(entry["event_type"], []).append(entry)

    order = [name for name in METRIC_PRIORITY if name in grouped]
    order.extend(name for name in grouped if name not in order)

    lines = [
        f"Metric observations ({len(metrics)} data points, summarized by signal):"
    ]
    for name in order:
        series = grouped[name]
        valued = [
            (entry, value)
            for entry in series
            if (value := _metric_value(entry)) is not None
        ]
        if not valued:
            lines.append(f"  {name}: {len(series)} samples, no numeric values")
            continue

        low = min(value for _, value in valued)
        peak_entry, peak = max(valued, key=lambda item: item[1])
        lines.append(
            f"  {name} service={peak_entry['service']} samples={len(valued)} "
            f"min={low:.4f} max={peak:.4f} peak_at={peak_entry['timestamp']} "
            f"peak_severity={peak_entry['severity']}"
        )
        for entry, _value in sorted(valued, key=lambda item: item[1], reverse=True)[:3]:
            lines.append(
                f"    [{entry['timestamp']}] [{entry['service']}] "
                f"{entry['severity']} {entry['content']}"
            )

    return "\n".join(lines)


def _format_traces(traces: list[dict[str, Any]]) -> str:
    """Show failed and slow spans before ordinary successful spans."""
    if not traces:
        return ""

    def rank(entry: dict[str, Any]) -> tuple[int, float]:
        failed = 0 if entry["severity"] in ("error", "critical") else 1
        duration = float((entry.get("metadata") or {}).get("duration_ms") or 0)
        return (failed, -duration)

    ordered = sorted(traces, key=rank)
    error_count = sum(1 for entry in traces if entry["severity"] in ("error", "critical"))
    lines = [
        f"Trace spans ({len(traces)} spans, {error_count} errors; "
        "failed and slowest spans first):"
    ]
    for entry in ordered[:MAX_TRACE_ENTRIES]:
        ts = entry["timestamp"]
        svc = entry["service"]
        lines.append(f"  [{ts}] [{svc}] {entry['severity']} {entry['content']}")
        meta = entry.get("metadata", {})
        if meta.get("trace_id"):
            lines.append(f"    trace_id={meta['trace_id']}")
        if meta.get("duration_ms"):
            lines.append(f"    duration={meta['duration_ms']}ms")
        if meta.get("status_code"):
            lines.append(f"    status_code={meta['status_code']}")

    if len(traces) > MAX_TRACE_ENTRIES:
        lines.append(f"  ... and {len(traces) - MAX_TRACE_ENTRIES} more spans")

    return "\n".join(lines)


def build_semantic_query(incident, evidence_rows: list) -> str:
    """Generate a natural-language semantic query from incident and evidence.

    This query is embedded and used to search the historical incident
    vector store for similar past incidents.
    """
    parts = []

    service = getattr(incident, "service", "unknown")
    title = getattr(incident, "title", "")
    description = getattr(incident, "description", "") or ""
    severity = getattr(incident, "severity", "")

    parts.append(f"{title}")
    if description:
        parts.append(description)

    error_keywords: list[str] = []
    for row in evidence_rows:
        if row.severity in ("error", "critical"):
            content = row.content[:200]
            if content not in error_keywords:
                error_keywords.append(content)
        if len(error_keywords) >= 5:
            break

    if error_keywords:
        parts.append("Key errors: " + "; ".join(error_keywords))

    event_types = set()
    for row in evidence_rows:
        if row.event_type and row.event_type != "collector_error":
            event_types.add(row.event_type)
    if event_types:
        parts.append(f"Event types observed: {', '.join(list(event_types)[:8])}")

    parts.append(f"Affected service: {service}, Severity: {severity}")

    query = " ".join(parts)
    logger.info("Generated semantic query: %s", query[:200])
    return query
