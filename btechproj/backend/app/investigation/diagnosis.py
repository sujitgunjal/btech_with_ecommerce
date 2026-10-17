"""Turn an RCA into an evidence-based diagnosis.

Experiment names stay in stored incident metadata. They are removed from the
text shown to operators unless that text is only describing a hypothesis.
"""

from __future__ import annotations

import re
from typing import Any

SCENARIO_IDS = (
    "cpu_high",
    "memory_pressure",
    "slow_responses",
    "elevated_5xx",
    "db_latency",
    "db_pool_exhaustion",
    "payment_timeout",
    "payment_failure",
    "inventory_conflict",
    "slow_search",
    "slow_checkout",
    "service_unavailable",
    "dependency_timeout",
    "browse_load",
    "search_load",
    "checkout_load",
    "mixed_load",
)

_SCENARIO_RE = re.compile(
    r"\b(" + "|".join(SCENARIO_IDS) + r")\b",
    re.IGNORECASE,
)
_EXPERIMENT_RE = re.compile(
    r"\b(experiment|injected fault|fault injection|intentional(?:ly)?|"
    r"scenario id|stop the (?:fault|experiment)|remove the (?:injected )?fault|"
    r"disable (?:the )?fault)\b",
    re.IGNORECASE,
)
_RESTART_RE = re.compile(
    r"\b(restart|reboot|roll(?:\s|-)?back|revert the deployment)\b",
    re.IGNORECASE,
)
_STILL_DOWN_RE = re.compile(
    r"health check failed|connection refused|status=down|still unavailable|"
    r"not recovering|crash loop",
    re.IGNORECASE,
)
_RECOVERED_RE = re.compile(
    r"\brecovered\b|status=ok|health check (?:passed|ok)|returned to baseline",
    re.IGNORECASE,
)


def sanitize_operator_text(text: str) -> str:
    """Remove experiment identifiers from text that will be shown or prompted."""
    cleaned = _SCENARIO_RE.sub("the observed condition", text or "")
    cleaned = _EXPERIMENT_RE.sub("", cleaned)
    cleaned = re.sub(
        r"\b(?:an?|the)\s+intentional\s+.*?experiment\b",
        "the observed condition",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\bfault experiment\b",
        "incident",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def refine_rca(rca: dict[str, Any], evidence_text: str) -> dict[str, Any]:
    """Rewrite experiment-centric diagnoses using the collected evidence."""
    evidence = evidence_text or ""
    found = detect_signals(evidence)
    root = str(rca.get("root_cause") or "")
    if _needs_rewrite(root) or not root.strip():
        root = build_diagnosis(found, evidence)
        if "Not established" in root or root.lower().startswith("hypothesis"):
            rca["confidence"] = min(float(rca.get("confidence") or 0.0), 0.55)
    else:
        root = sanitize_operator_text(root)
        if found and "not established" not in root.lower():
            root = f"{root} {build_diagnosis(found, evidence)}".strip()
    rca["root_cause"] = root
    rca["recommended_actions"] = refine_actions(
        list(rca.get("recommended_actions") or []),
        found,
        evidence,
    )
    rca["alternative_explanations"] = [
        sanitize_operator_text(item)
        for item in rca.get("alternative_explanations") or []
        if item and not _is_experiment_only(str(item))
    ]
    timeline = []
    for entry in rca.get("timeline") or []:
        if not isinstance(entry, dict):
            continue
        event = sanitize_operator_text(str(entry.get("event") or ""))
        if _is_experiment_only(event):
            continue
        timeline.append({"timestamp": str(entry.get("timestamp") or ""), "event": event})
    rca["timeline"] = timeline
    rca["supporting_evidence"] = [
        sanitize_operator_text(item)
        for item in rca.get("supporting_evidence") or []
        if item and not _is_experiment_only(str(item))
    ]
    return rca


def detect_signals(evidence_text: str) -> set[str]:
    text = (evidence_text or "").lower()
    found: set[str] = set()
    if any(token in text for token in ("memory", "working set", "working_set")):
        found.add("memory")
    if "cpu" in text:
        found.add("cpu")
    if any(token in text for token in ("payment", "gateway", "504")):
        found.add("payment")
    if any(token in text for token in ("database", "sql ", "sqlalchemy", "pool")):
        found.add("database")
    if any(token in text for token in ("503", "unavailable", "connection refused")):
        found.add("unavailable")
    if any(token in text for token in ("5xx", "status=500", " http 500", "error_rate")):
        found.add("errors")
    if any(token in text for token in ("latency", "duration=", "p95", "slow")):
        found.add("latency")
    return found


def build_diagnosis(found: set[str], evidence_text: str) -> str:
    if not found:
        return (
            "Hypothesis: the available logs, metrics, and traces do not confirm "
            "a specific technical condition. Not established: a root cause."
        )
    parts: list[str] = []
    if "memory" in found:
        parts.append(
            "Confirmed: process memory usage rose during the window. "
            "Not established: which allocation or limit caused it."
        )
    if "cpu" in found:
        parts.append(
            "Confirmed: CPU usage increased and overlapped higher request latency. "
            "Not established: which code path consumed the CPU."
        )
    if "payment" in found:
        parts.append(
            "Confirmed: checkout calls to the payment gateway exceeded the caller "
            "timeout or returned a gateway error. Not established: why the gateway "
            "was slow or failing."
        )
    if "database" in found:
        parts.append(
            "Confirmed: database statements or connection waits were slower than "
            "the rest of the request. Not established: whether the database, the "
            "pool, or the query shape was responsible."
        )
    if "errors" in found:
        parts.append(
            "Confirmed: a portion of requests returned HTTP 5xx. "
            "Not established: the exception behind those responses, unless an "
            "error log states it."
        )
    if "unavailable" in found:
        parts.append(
            "Confirmed: callers received HTTP 503 or could not connect. "
            "Not established: whether the process crashed or stopped accepting work."
        )
    if "latency" in found and not ({"payment", "database", "cpu"} & found):
        parts.append(
            "Confirmed: request latency increased. Not established: whether the "
            "delay was inside this service or a dependency."
        )
    if _RECOVERED_RE.search(evidence_text or "") and not _STILL_DOWN_RE.search(evidence_text or ""):
        parts.append("Confirmed: later samples show the service recovered.")
    return " ".join(parts)


def refine_actions(actions: list[str], found: set[str], evidence_text: str) -> list[str]:
    recovered = bool(_RECOVERED_RE.search(evidence_text or "")) and not bool(
        _STILL_DOWN_RE.search(evidence_text or "")
    )
    still_down = bool(_STILL_DOWN_RE.search(evidence_text or ""))
    kept: list[str] = []
    for action in actions:
        text = str(action).strip()
        if not text or _EXPERIMENT_RE.search(text) or _SCENARIO_RE.search(text):
            continue
        if _RESTART_RE.search(text) and (recovered or not still_down):
            continue
        kept.append(sanitize_operator_text(text))
    suggested = suggested_actions(found, recovered=recovered, still_down=still_down)
    merged: list[str] = []
    for item in suggested + kept:
        if item and item not in merged:
            merged.append(item)
    return merged[:6]


def suggested_actions(
    found: set[str],
    *,
    recovered: bool,
    still_down: bool,
) -> list[str]:
    actions: list[str] = []
    if "memory" in found:
        actions.append(
            "Review the memory trend for this service across the incident window and compare it with the configured memory limit."
        )
    if "cpu" in found:
        actions.append(
            "Compare CPU usage with request latency and identify the slowest operation in the traces before changing capacity."
        )
    if "payment" in found:
        actions.append(
            "Compare payment-gateway latency and error rate with the shop checkout timeout. Treat them as separate signals."
        )
    if "database" in found:
        actions.append(
            "Inspect the slow SQL spans and database connection waits, then check database CPU and lock time for the same window."
        )
    if "errors" in found:
        actions.append(
            "Read the error logs for the failing route and compare the 5xx rate with total request rate."
        )
    if "unavailable" in found:
        actions.append(
            "Check whether the service health endpoint is reachable now and whether dependents are still receiving connection errors."
        )
    if "latency" in found:
        actions.append(
            "Split latency by endpoint and dependency span so a slow dependency is not treated as a slow local handler."
        )
    if still_down:
        actions.append(
            "Restart the service only if it is still failing health checks or not making progress."
        )
    elif recovered:
        actions.append(
            "Do not restart the service. Confirm the latency, error rate, and resource series have returned to baseline."
        )
    if not actions:
        actions.append(
            "Collect another evidence window before changing the service. The current signals do not justify a restart."
        )
    return actions


def _needs_rewrite(root_cause: str) -> bool:
    return bool(_EXPERIMENT_RE.search(root_cause) or _SCENARIO_RE.search(root_cause))


def _is_experiment_only(text: str) -> bool:
    if not (_EXPERIMENT_RE.search(text) or _SCENARIO_RE.search(text)):
        return False
    stripped = sanitize_operator_text(text)
    return len(stripped) < 40
