"""Answer a question about one incident using only collected investigation context.

This does not start a second model pipeline. Callers pass the incident, the
existing RCA, and the evidence already returned by the collectors.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

SUGGESTED_QUESTIONS = [
    "Why does the system suspect this cause?",
    "Which evidence supports this conclusion?",
    "What other causes are possible?",
]

_EXPERIMENT_RE = re.compile(
    r"\b(memory_pressure|cpu_high|payment_timeout|slow_responses|db_latency|"
    r"service_unavailable|elevated_5xx|injected fault|fault injection|fault experiment|"
    r"experiment)\b",
    re.IGNORECASE,
)
_FAULT_PATH_RE = re.compile(r"/?internal/faults\S*", re.IGNORECASE)


def build_chat_messages(
    *,
    question: str,
    history: list[dict[str, str]],
    incident: dict[str, Any],
    report: dict[str, Any] | None,
    evidence_text: str,
    historical_note: str = "",
) -> list[dict[str, str]]:
    system = (
        "You answer questions about one DevOps incident. "
        "Use only the incident, root-cause report, logs, metrics, traces, "
        "correlations, alternative explanations, and historical incidents provided. "
        "Historical incidents are context, not proof. "
        "Say when evidence is insufficient. "
        "Label a statement as verified only when the provided evidence states it, "
        "and as a hypothesis when it does not. "
        "Do not invent metrics, logs, traces, span names, durations, or trace IDs. "
        "Historical incidents are contextual examples, not proof of this incident. "
        "An earlier request does not prove a configuration change or a cause. "
        "Rank only causes the evidence supports, and do not add a hypothesis to fill a requested count. "
        "cpu_usage from this collector is cores, from rate(container_cpu_usage_seconds_total), not a percentage and not saturation. "
        "Saturation requires a CPU limit and a throttling series, which this collector does not store. "
        "Answer from the collected rows. Name Jaeger or Prometheus only for a field those rows do not contain. "
        "Do not mention experiment names. "
        "Reply with JSON: "
        '{"answer":"string","certainty":"verified|hypothesis|insufficient",'
        '"evidence_refs":[{"source":"logs|metrics|traces|correlations","index":0,"label":"short name"}]}'
    )
    context = {
        "incident": {
            "service": incident.get("service"),
            "severity": incident.get("severity"),
            "title": incident.get("title"),
            "description": incident.get("description"),
            "start_time": incident.get("start_time"),
            "end_time": incident.get("end_time"),
        },
        "report": report or {},
        "historical_incidents": historical_note or "None retrieved. These are never proof.",
        "evidence": evidence_text or "No telemetry was collected.",
    }
    messages = [{"role": "system", "content": system}]
    for turn in history[-6:]:
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content[:2000]})
    messages.append(
        {
            "role": "user",
            "content": (
                "Incident context:\n"
                + json.dumps(context, default=str)[:12000]
                + "\n\nQuestion: "
                + question.strip()
            ),
        }
    )
    return messages


def asks_for_procedure(question: str) -> bool:
    text = (question or "").lower()
    if re.search(r"\bhow (do|can|should|to|would)\b", text):
        return True
    if re.search(r"\b(steps|walk me through|carry out|perform)\b", text):
        return True
    return "recommended" in text and bool(re.search(r"\b(how|steps|check|investigate)\b", text))


def rows_from_stored(rows: list[dict]) -> dict[str, list]:
    """Turn saved investigation evidence into the chat's structured lists."""
    grouped: dict[str, list] = {"logs": [], "metrics": [], "traces": [], "correlations": []}
    for row in rows:
        source = str(row.get("source") or "").lower()
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        if source == "jaeger" or row.get("event_type") == "trace":
            grouped["traces"].append(
                {
                    "timestamp": row.get("timestamp"),
                    "service": row.get("service"),
                    "operation": meta.get("operation"),
                    "duration_ms": meta.get("duration_ms"),
                    "trace_id": meta.get("trace_id"),
                    "span_id": meta.get("span_id"),
                    "parent_span_id": meta.get("parent_span_id"),
                    "tags": meta.get("tags") or {},
                    "status": row.get("severity"),
                }
            )
        elif source == "prometheus":
            grouped["metrics"].append(
                {
                    "timestamp": row.get("timestamp"),
                    "service": row.get("service"),
                    "metric_name": row.get("event_type"),
                    "value": meta.get("value"),
                    "labels": meta.get("labels") or {},
                }
            )
        elif source == "correlation":
            grouped["correlations"].append(
                {
                    "timestamp": row.get("timestamp"),
                    "service": row.get("service"),
                    "content": row.get("content"),
                    "relation": meta.get("relation"),
                }
            )
        else:
            grouped["logs"].append(
                {
                    "timestamp": row.get("timestamp"),
                    "service": row.get("service"),
                    "message": row.get("content"),
                    "level": row.get("severity"),
                }
            )
    return grouped


_METRIC_UNITS = {
    "cpu_usage": (
        "cores, from the collector query sum(rate(container_cpu_usage_seconds_total[1m])). "
        "That is CPU-seconds per second, not a percentage of a limit"
    ),
    "memory_usage": "bytes of container working set (container_memory_working_set_bytes)",
    "latency": "seconds, from the collector latency histogram",
    "request_latency": "seconds, from the collector latency histogram",
    "db_query_latency": "seconds, from ecommerce_db_query_duration",
    "error_rate": "errors per second from the collector error counter, not a percentage unless the row says so",
    "request_rate": "requests per second from the collector request counter",
}


def classify_question(question: str) -> str | None:
    text = (question or "").lower()
    if asks_for_procedure(text):
        return "procedure"
    if re.search(r"\b(trace|traces|span|spans|slowest)\b", text):
        return "traces"
    if re.search(r"\b(caused|causation|prove|preced|cause the|cause this|cause that)\b", text):
        return "causal"
    if re.search(r"\b(cpu|saturation|throttl|metric units|what does .* mean)\b", text):
        return "metrics"
    if re.search(r"\b(why|other causes|possible causes|plausible|hypothes)\b", text):
        return "hypothesis"
    if re.search(r"\b(caused|causation|prove|preced)\b", text):
        return "causal"
    return None


def grounded_answer(
    question: str,
    incident: dict[str, Any],
    report: dict[str, Any] | None,
    evidence: dict[str, list],
) -> dict[str, Any] | None:
    kind = classify_question(question)
    if kind == "traces":
        return trace_answer(incident, evidence)
    if kind == "metrics":
        return metric_answer(incident, evidence)
    if kind == "hypothesis":
        return hypothesis_answer(incident, report, evidence)
    if kind == "causal":
        return causal_answer(incident, evidence)
    if kind == "procedure":
        return procedure_answer(question, incident, report, evidence)
    return None


def trace_answer(incident: dict[str, Any], evidence: dict[str, list]) -> dict[str, Any]:
    service = incident.get("service") or ""
    traces = [row for row in (evidence.get("traces") or []) if isinstance(row, dict)]
    if not traces:
        return {
            "answer": (
                "No spans were stored for this incident. The missing fields are operation, "
                "duration_ms, trace_id, timestamp, and service. This collector path did not "
                "return Jaeger rows, so no trace id or duration can be quoted. "
                "Jaeger at http://localhost:16686 still has to be queried for "
                f"{service or 'the service'} between {incident.get('start_time')} and {incident.get('end_time')}."
            ),
            "certainty": "insufficient",
            "evidence_refs": [],
        }
    ranked, skipped = _rank_spans(traces, service, incident.get("start_time"), incident.get("end_time"))
    if not ranked:
        return {
            "answer": (
                f"Spans were stored, but none have both a timestamp inside the incident window "
                f"and a duration_ms value for {service or 'the incident service'}. "
                f"Skipped rows: {skipped or 'none'}. No operation ranking is possible from the saved fields."
            ),
            "certainty": "insufficient",
            "evidence_refs": [],
        }
    lines = [
        f"Slowest collected operations for {service or 'the incident service'} "
        f"between {incident.get('start_time')} and {incident.get('end_time')}. "
        "duration_ms is the span duration stored by the Jaeger collector. "
        "Where a start timestamp exists, the end time below is that start plus duration_ms, "
        "which is a calculation from those two stored fields.",
    ]
    refs = []
    for item in ranked[:5]:
        lines.append(
            f"- {item['operation']} on {item['service']}: {item['duration_ms']} ms, "
            f"trace_id {item['trace_id']}, start {item['timestamp']}, calculated end {item['end']}."
        )
        refs.append({"source": "traces", "index": item["index"], "label": item["operation"][:80]})
    if skipped:
        lines.append("Rows left out: " + "; ".join(skipped) + ".")
    if any(row.get("parent_span_id") for row in traces):
        lines.append("Some spans include parent_span_id, so a parent and its children can be compared directly.")
    else:
        lines.append(
            "parent_span_id was not stored on these span rows. The saved fields are operation, "
            "duration_ms, trace_id, span_id, timestamp, service, and tags. A parent-child split "
            "cannot be calculated from this table. The same trace_id can be opened in Jaeger at "
            "http://localhost:16686 if that trace is still retained."
        )
    return {"answer": "\n".join(lines), "certainty": "verified", "evidence_refs": refs}


def metric_answer(incident: dict[str, Any], evidence: dict[str, list]) -> dict[str, Any]:
    service = incident.get("service") or ""
    metrics = [row for row in (evidence.get("metrics") or []) if isinstance(row, dict)]
    chosen = [row for row in metrics if not service or row.get("service") in {None, "", service}]
    if not chosen:
        return {
            "answer": (
                "No Prometheus samples were stored for this service. A missing series is not a "
                "measured zero. CPU saturation is not established: the stored evidence has neither "
                "a CPU limit nor container_cpu_cfs_throttled_seconds_total. Those series were not "
                "part of the collector result for this incident."
            ),
            "certainty": "insufficient",
            "evidence_refs": [],
        }
    by_name: dict[str, list[tuple[int, dict]]] = {}
    for index, row in enumerate(metrics):
        if service and row.get("service") not in {None, "", service}:
            continue
        by_name.setdefault(str(row.get("metric_name") or "unnamed"), []).append((index, row))
    lines = []
    refs = []
    names = set(by_name)
    if "cpu_usage" in names:
        lines.append(
            "cpu_usage is " + _METRIC_UNITS["cpu_usage"] + ". "
            "The stored labels on these rows do not include the raw Prometheus metric name. "
            "CPU saturation is not established, because no CPU limit and no "
            "container_cpu_cfs_throttled_seconds_total sample were collected."
        )
    for name, rows in by_name.items():
        numeric = [(index, row) for index, row in rows if isinstance(row.get("value"), (int, float))]
        if not numeric:
            lines.append(f"{name} was stored without a numeric value.")
            continue
        index, peak = max(numeric, key=lambda item: item[1]["value"])
        unit = _METRIC_UNITS.get(name, "the collector did not record a unit on this alias")
        lines.append(
            f"Highest stored {name} for {peak.get('service') or service} is {peak['value']} ({unit}) "
            f"at {peak.get('timestamp')}."
        )
        refs.append({"source": "metrics", "index": index, "label": name[:80]})
    if "cpu_usage" in names and "container_cpu_cfs_throttled_seconds_total" not in names:
        lines.append(
            "Do not read a value such as 0.5333 as 53 percent or as a saturated CPU. "
            "It is the recorded core rate at that timestamp."
        )
    return {"answer": "\n".join(lines), "certainty": "verified", "evidence_refs": refs}


def hypothesis_answer(
    incident: dict[str, Any],
    report: dict[str, Any] | None,
    evidence: dict[str, list],
) -> dict[str, Any]:
    service = incident.get("service") or "the service"
    ranked, _skipped = _rank_spans(
        [row for row in (evidence.get("traces") or []) if isinstance(row, dict)],
        service,
        incident.get("start_time"),
        incident.get("end_time"),
    )
    operations = {item["operation"] for item in ranked}
    cpu = _peak_metric(evidence.get("metrics") or [], "cpu_usage", service)
    lines = [f"Causes are ranked only when this incident's evidence supports them. Service: {service}."]
    supported = 0
    if cpu is not None:
        lines.append(
            f"Confirmed observation, not a cause: cpu_usage reached {cpu['value']} cores "
            f"at {cpu.get('timestamp')}. {_METRIC_UNITS['cpu_usage']}. "
            "This does not establish saturation."
        )
        supported += 0
    business = [name for name in operations if name and "health" not in name and "internal/faults" not in name]
    if operations and not business:
        lines.append(
            "Not ranked: a business-traffic surge. The collected operations are "
            + ", ".join(sorted(operations)[:6])
            + ". Health and status spans do not show a customer-request surge, so that recorded "
            "alternative is contradicted by the span list."
        )
    elif business:
        lines.append(
            "Hypothesis, low confidence: more work on " + ", ".join(business[:3])
            + ". Support is only that those operations appear in the window. "
            "Missing evidence: a request-rate series tied to those routes, and a comparison with the CPU limit."
        )
        supported += 1
    lines.append(
        "Not ranked: an operator request or a configuration change as the cause. "
        "A request that happens earlier is temporal correlation. It does not prove the request "
        "changed configuration or raised CPU. The validating check is to compare the stored "
        "cpu_usage samples before and after that request; the samples show the values, not the cause. "
        "A throttling series was not collected."
    )
    recorded = (report or {}).get("alternative_explanations") or []
    if recorded and supported == 0:
        lines.append(
            f"The report recorded {len(recorded)} alternative explanation(s). "
            "None is promoted to a ranked cause beyond the points above. "
            "No extra hypothesis is added to fill a count."
        )
    elif supported == 0:
        lines.append("No cause is supported strongly enough to rank. No extra hypothesis is added.")
    refs = []
    if cpu and cpu.get("index") is not None:
        refs.append({"source": "metrics", "index": cpu["index"], "label": "cpu_usage"})
    if ranked:
        refs.append({"source": "traces", "index": ranked[0]["index"], "label": ranked[0]["operation"][:80]})
    return {
        "answer": _strip_experiment_terms("\n".join(lines)),
        "certainty": "hypothesis",
        "evidence_refs": refs[:6],
    }


def causal_answer(incident: dict[str, Any], evidence: dict[str, list]) -> dict[str, Any]:
    service = incident.get("service") or "the service"
    logs = [row for row in (evidence.get("logs") or []) if isinstance(row, dict)]
    cpu_rows = [
        (index, row)
        for index, row in enumerate(evidence.get("metrics") or [])
        if isinstance(row, dict)
        and row.get("metric_name") == "cpu_usage"
        and (not service or row.get("service") in {None, "", service})
        and isinstance(row.get("value"), (int, float))
    ]
    lines = [
        "Confirmed and hypothesized findings are separate. Temporal order is not causation.",
    ]
    refs = []
    if cpu_rows:
        first = min(cpu_rows, key=lambda item: str(item[1].get("timestamp") or ""))
        peak = max(cpu_rows, key=lambda item: item[1]["value"])
        lines.append(
            f"Confirmed: cpu_usage for {service} is recorded as {first[1]['value']} cores "
            f"at {first[1].get('timestamp')} and {peak[1]['value']} cores at {peak[1].get('timestamp')}. "
            + _METRIC_UNITS["cpu_usage"]
            + ". Saturation is not confirmed."
        )
        refs.append({"source": "metrics", "index": peak[0], "label": "cpu_usage"})
    else:
        lines.append("Unknown: no cpu_usage sample was stored, so a CPU change cannot be confirmed.")
    operator = next(
        (
            (index, row)
            for index, row in enumerate(logs)
            if "internal/faults" in str(row.get("message") or "") or "operator" in str(row.get("message") or "").lower()
        ),
        None,
    )
    if operator:
        index, row = operator
        lines.append(
            f"Confirmed: a request was logged at {row.get('timestamp')} on {row.get('service')}: "
            f"{_clip(str(row.get('message') or ''), 180)}."
        )
        refs.append({"source": "logs", "index": index, "label": "operator request"})
        lines.append(
            "Hypothesis, not confirmed: that this request changed configuration or caused the CPU values. "
            "The evidence supports only that the request happened and that CPU samples exist. "
            "It contradicts treating the request as proof. The next check is the stored CPU samples "
            "around that timestamp, plus a throttling series that was not collected."
        )
    else:
        lines.append(
            "No operator-request log was stored. A cause cannot be assigned from timing alone."
        )
    return {"answer": _strip_experiment_terms("\n".join(lines)), "certainty": "hypothesis", "evidence_refs": refs[:6]}


def _rank_spans(traces: list[dict], service: str, start: Any, end: Any) -> tuple[list[dict], list[str]]:
    start_dt = _parse_time(start)
    end_dt = _parse_time(end)
    best: dict[str, dict] = {}
    skipped: list[str] = []
    for index, span in enumerate(traces):
        span_service = span.get("service") or ""
        if service and span_service and span_service != service:
            continue
        if service and not span_service:
            skipped.append(f"index {index} missing service")
            continue
        stamp = _parse_time(span.get("timestamp"))
        if start_dt and stamp and stamp < start_dt:
            continue
        if end_dt and stamp and stamp > end_dt:
            continue
        if (start_dt or end_dt) and stamp is None:
            skipped.append(f"index {index} missing timestamp")
            continue
        duration = span.get("duration_ms")
        if not isinstance(duration, (int, float)):
            skipped.append(f"index {index} missing duration_ms")
            continue
        operation = span.get("operation") or "unnamed operation"
        current = best.get(operation)
        if current is None or duration > current["duration_ms"]:
            end_text = "not calculated"
            if stamp is not None:
                end_text = (stamp + timedelta(milliseconds=float(duration))).isoformat()
            best[operation] = {
                "operation": operation,
                "service": span_service or service,
                "duration_ms": duration,
                "trace_id": span.get("trace_id") or "not stored",
                "timestamp": span.get("timestamp"),
                "end": end_text,
                "index": index,
            }
    ranked = sorted(best.values(), key=lambda item: item["duration_ms"], reverse=True)
    return ranked, skipped[:6]


def _peak_metric(metrics: list, name: str, service: str) -> dict | None:
    best = None
    for index, row in enumerate(metrics):
        if not isinstance(row, dict) or row.get("metric_name") != name:
            continue
        if service and row.get("service") not in {None, "", service}:
            continue
        if not isinstance(row.get("value"), (int, float)):
            continue
        if best is None or row["value"] > best["value"]:
            best = {"value": row["value"], "timestamp": row.get("timestamp"), "index": index}
    return best


def _parse_time(value: Any):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def procedure_answer(
    question: str,
    incident: dict[str, Any],
    report: dict[str, Any] | None,
    evidence: dict[str, list],
) -> dict[str, Any]:
    """Explain how to carry out a check with Jaeger and Prometheus.

    Durations and span names are copied from collected evidence. Tool locations
    and the shop-to-payment call path come from the deployed system, not from
    a measured result.
    """
    service = incident.get("service") or "the affected service"
    start = incident.get("start_time") or "the incident start"
    end = incident.get("end_time") or "the incident end, which was not recorded"
    traces = [row for row in (evidence.get("traces") or []) if isinstance(row, dict)]
    metrics = [row for row in (evidence.get("metrics") or []) if isinstance(row, dict)]
    actions = [_strip_experiment_terms(str(item)) for item in ((report or {}).get("recommended_actions") or [])]
    actions = [item for item in actions if item][:3]
    refs: list[dict[str, Any]] = []
    lines = [
        f"Collected evidence for {service} from {start} to {end} is used first. "
        "Historical incidents are not proof.",
    ]
    if actions:
        lines.append("Recorded recommendation: " + " ".join(actions))
    lines.extend(_trace_steps(service, traces, refs))
    lines.extend(_metric_steps(service, metrics, refs))
    lines.append(
        "The shop charges ecommerce-payment-gateway with POST /charges, and that client "
        "timeout is the configured PAYMENT_TIMEOUT_SECONDS value (2 seconds unless the "
        "environment overrides it). That is the application path, not a duration measured "
        "for this incident. Compare it with a Jaeger child span only when that span was collected."
    )
    return {
        "answer": "\n".join(lines),
        "certainty": "procedure",
        "evidence_refs": refs[:6],
    }


def _trace_steps(service: str, traces: list[dict], refs: list[dict]) -> list[str]:
    lines = []
    if not traces:
        lines.append(
            "No spans were stored, so endpoint, local, and dependency durations cannot be quoted. "
            "Missing fields: operation, duration_ms, trace_id, parent_span_id. "
            "Jaeger at http://localhost:16686 can be queried for "
            f"{service} in this window; that data is not in the incident evidence."
        )
        return lines
    else:
        lines.append(
            "Endpoint duration is the collected server span. Dependency time is a collected child "
            "span on another service. Local processing is the server duration minus those child "
            "durations when parent_span_id is stored. It is a calculation, not another metric."
        )
    sample = traces[:3]
    described = []
    for index, span in enumerate(sample):
        operation = span.get("operation") or "unnamed operation"
        span_service = span.get("service") or service
        duration = span.get("duration_ms")
        duration_text = f", recorded duration {duration} ms" if isinstance(duration, (int, float)) else ", no duration was stored on this span"
        described.append(f"{operation} on {span_service}{duration_text}")
        refs.append({"source": "traces", "index": index, "label": str(operation)[:80]})
    lines.append("Collected spans to open first: " + "; ".join(described) + ".")
    parent = next(
        (
            span for span in traces
            if span.get("span_id")
            and isinstance(span.get("duration_ms"), (int, float))
            and any(
                child.get("parent_span_id") == span.get("span_id")
                and child.get("trace_id") == span.get("trace_id")
                for child in traces
            )
        ),
        None,
    )
    if parent and parent.get("duration_ms") is not None and parent.get("span_id"):
        children = [
            span for span in traces
            if span.get("parent_span_id") == parent.get("span_id")
            and span.get("trace_id") == parent.get("trace_id")
            and isinstance(span.get("duration_ms"), (int, float))
        ]
        if children and isinstance(parent.get("duration_ms"), (int, float)):
            shown = children[:4]
            remainder = parent["duration_ms"] - sum(span["duration_ms"] for span in shown)
            child_text = ", ".join(
                f"{span.get('operation') or 'child'} on {span.get('service') or 'unknown'} {span['duration_ms']} ms"
                for span in shown
            )
            extra = len(children) - len(shown)
            extra_text = (
                f" {extra} more child spans were collected and are not included in this subtraction."
                if extra
                else ""
            )
            lines.append(
                f"For collected trace {parent.get('trace_id')}, server span "
                f"{parent.get('operation') or 'request'} is {parent['duration_ms']} ms and the "
                f"recorded children used here are {child_text}. Subtracting those child durations leaves "
                f"{remainder} ms. That remainder is calculated from these collected spans.{extra_text}"
            )
        else:
            lines.append(
                "The collected spans do not include a parent span id linked to child spans, "
                "so the local-processing remainder cannot be calculated from this page. "
                "Open the same trace id in Jaeger, where the timeline keeps that parent-child link."
            )
    return lines


def _metric_steps(service: str, metrics: list[dict], refs: list[dict]) -> list[str]:
    lines = []
    if not metrics:
        lines.append(
            "No Prometheus samples were stored. An absent series is not a measured zero. "
            "The collector aliases are cpu_usage (cores, rate of container_cpu_usage_seconds_total), "
            "memory_usage (bytes), and latency (seconds). CPU saturation cannot be claimed without "
            "a limit and container_cpu_cfs_throttled_seconds_total, which were not stored. "
            "Prometheus at http://localhost:9090 is only needed for a series this incident did not collect."
        )
        return lines
    names = []
    for index, row in enumerate(metrics[:4]):
        name = row.get("metric_name") or "unnamed metric"
        value = row.get("value")
        if isinstance(value, (int, float)):
            names.append(f"{name} recorded value {value}")
        else:
            names.append(f"{name} with no stored value")
        refs.append({"source": "metrics", "index": index, "label": str(name)[:80]})
    lines.append("Collected metric rows: " + "; ".join(names) + ".")
    return lines


def fallback_answer(question: str, report: dict[str, Any] | None, evidence_text: str) -> dict[str, Any]:
    """Answer without the model when it is unavailable. Do not invent numbers."""
    if not (evidence_text or "").strip() and not report:
        return {
            "answer": (
                "There is not enough evidence to answer that. "
                "No root-cause report or telemetry has been collected for this incident yet."
            ),
            "certainty": "insufficient",
            "evidence_refs": [],
        }
    root = (report or {}).get("root_cause") or ""
    alternatives = (report or {}).get("alternative_explanations") or []
    actions = (report or {}).get("recommended_actions") or []
    lowered = question.lower()
    if "other cause" in lowered or "possible" in lowered:
        if alternatives:
            body = "Hypothesis only: " + " ".join(str(item) for item in alternatives[:3])
            certainty = "hypothesis"
        else:
            body = "No alternative explanations were recorded. That absence is not proof of a single cause."
            certainty = "insufficient"
    elif "evidence" in lowered or "support" in lowered:
        if evidence_text.strip():
            body = "The collected telemetry is available on this page. " + _clip(evidence_text)
            certainty = "verified"
        else:
            body = "No logs, metrics, or traces were collected, so nothing supports a conclusion yet."
            certainty = "insufficient"
    elif root:
        body = "From the recorded analysis: " + root
        certainty = "hypothesis" if "not established" in root.lower() or "hypothesis" in root.lower() else "verified"
    else:
        body = "The investigation did not record a root cause, and there is not enough evidence to infer one."
        certainty = "insufficient"
    if actions and "what should" in lowered:
        body += " Recorded checks: " + " ".join(str(item) for item in actions[:3])
    return {"answer": _strip_experiment_terms(body), "certainty": certainty, "evidence_refs": []}


def parse_model_answer(raw: str | None, evidence: dict[str, list]) -> dict[str, Any]:
    """Keep only citations that point at evidence the caller actually supplied."""
    data = _json_object(raw)
    if not data:
        return fallback_answer("", None, "")
    certainty = str(data.get("certainty") or "hypothesis")
    if certainty not in {"verified", "hypothesis", "insufficient"}:
        certainty = "hypothesis"
    answer = _strip_experiment_terms(str(data.get("answer") or "")).strip()
    if not answer:
        return fallback_answer("", None, "")
    refs = []
    for item in data.get("evidence_refs") or []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "")
        rows = evidence.get(source)
        if not isinstance(rows, list):
            continue
        try:
            index = int(item["index"])
        except (KeyError, TypeError, ValueError):
            continue
        if index < 0 or index >= len(rows):
            continue
        label = _strip_experiment_terms(str(item.get("label") or source))[:80]
        refs.append({"source": source, "index": index, "label": label or source})
    has_evidence = any(isinstance(rows, list) and rows for rows in evidence.values())
    if certainty == "verified" and not refs:
        certainty = "hypothesis" if has_evidence else "insufficient"
    return {"answer": answer, "certainty": certainty, "evidence_refs": refs[:6]}


def _json_object(raw: str | None) -> dict | None:
    if not raw:
        return None
    text = raw.strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None


def _strip_experiment_terms(text: str) -> str:
    cleaned = _EXPERIMENT_RE.sub("", text or "")
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def evidence_brief(evidence: dict[str, list]) -> str:
    """Structured evidence for the model, not just a name."""
    lines = []
    for source, rows in evidence.items():
        indexed = [(index, row) for index, row in enumerate(rows) if isinstance(row, dict)]
        if source == "traces":
            indexed = sorted(
                indexed,
                key=lambda item: item[1].get("duration_ms") if isinstance(item[1].get("duration_ms"), (int, float)) else -1,
                reverse=True,
            )[:8]
        else:
            indexed = indexed[:8]
        for index, row in indexed:
            if source == "traces":
                detail = (
                    f"{row.get('operation')} service={row.get('service')} "
                    f"duration_ms={row.get('duration_ms')} trace_id={row.get('trace_id')} "
                    f"timestamp={row.get('timestamp')}"
                )
            elif source == "metrics":
                detail = (
                    f"{row.get('metric_name')} value={row.get('value')} "
                    f"service={row.get('service')} timestamp={row.get('timestamp')} "
                    f"labels={row.get('labels')}"
                )
            else:
                detail = row.get("message") or row.get("content") or row.get("metric_name") or row.get("operation") or source
            lines.append(f"[{source} #{index}] {detail}")
    return "\n".join(lines)


def _clip(text: str, limit: int = 500) -> str:
    compact = " ".join(text.split())
    return compact[:limit]
