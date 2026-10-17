"""Turn Prometheus counter increases into card metrics.

A missing series is unknown. A counter that did not increase means there were
no requests in the window, so latency and error rate stay unknown. Zero latency
or a zero error rate is returned only when requests were actually counted.
"""

from __future__ import annotations

WINDOW_MINUTES = 15


def summarize_service_traffic(
    *,
    telemetry_present: bool,
    request_count: float | None,
    error_count: float | None,
    duration_total: float | None,
    duration_unit: str,
) -> dict[str, float | None]:
    if not telemetry_present and request_count is None:
        return {
            "requests_per_minute": None,
            "average_latency_ms": None,
            "error_rate": None,
        }

    requests = _finite(request_count)
    if requests is None or requests <= 0:
        return {
            "requests_per_minute": 0.0 if telemetry_present or requests == 0 else None,
            "average_latency_ms": None,
            "error_rate": None,
        }

    errors = _finite(error_count)
    error_rate = 0.0 if errors is None else round(max(errors, 0.0) / requests * 100, 2)
    duration = _finite(duration_total)
    if duration is None:
        latency = None
    else:
        milliseconds = duration if duration_unit == "ms" else duration * 1000
        latency = round(max(milliseconds, 0.0) / requests, 1)

    return {
        "requests_per_minute": round(requests / WINDOW_MINUTES, 1),
        "average_latency_ms": latency,
        "error_rate": error_rate,
    }


def _finite(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in {float("inf"), float("-inf")}:
        return None
    return number
