"""Jaeger distributed tracing collector for incident evidence collection.

Retrieves traces and spans for a service and its dependencies within the incident
time window, returning structured trace/span records with trace ID, span ID,
service, operation, duration, status, and timestamp.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

try:
    from app.config import get_settings
    from app.schemas.evidence import NormalizedEvent
    from .base import BaseCollector
except ImportError:
    from backend.app.config import get_settings
    from backend.app.schemas.evidence import NormalizedEvent
    from backend.app.collectors.base import BaseCollector

logger = logging.getLogger("incident-backend")


class JaegerCollector(BaseCollector):
    """Collector for Jaeger distributed traces."""

    DEPENDENCY_MAP: dict[str, list[str]] = {
        "order-service": ["product-service", "user-service"],
        "product-service": ["user-service", "postgres"],
        "user-service": ["postgres"],
        "postgres": ["order-service", "product-service", "user-service"],
        "dependency-proxy": ["product-service", "order-service"],
        "ecommerce-shop-api": ["ecommerce-payment-gateway"],
        "ecommerce-payment-gateway": ["ecommerce-shop-api"],
    }

    def __init__(self, base_url: str | None = None, timeout: float = 10.0) -> None:
        if not base_url:
            base_url = get_settings().JAEGER_URL
        super().__init__(base_url=base_url, timeout=timeout)

    @staticmethod
    def _parse_time_to_microseconds(dt_input: datetime | str) -> int:
        """Convert a datetime or ISO string to unix microseconds."""
        if isinstance(dt_input, str):
            clean_str = dt_input.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)
        else:
            dt = dt_input

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1_000_000)

    async def get_traces(
        self,
        service: str,
        start_time: datetime | str,
        end_time: datetime | str,
        limit: int = 50,
        include_dependencies: bool = True,
    ) -> list[dict[str, Any]]:
        """Retrieve structured trace/span records for a service and time window.

        Args:
            service: Target service name.
            start_time: Start of incident window.
            end_time: End of incident window.
            limit: Maximum traces to fetch per service query.
            include_dependencies: Whether to also query known dependent services.

        Returns a list of structured span records:
            - source: "jaeger"
            - trace_id: trace identifier
            - span_id: span identifier
            - parent_span_id: parent span ID or None
            - service: service name of the span
            - operation: operation name
            - duration_ms: duration in milliseconds
            - status: "error" or "ok"
            - timestamp: ISO-8601 string
            - tags: dict of span tags
        """
        start_us = self._parse_time_to_microseconds(start_time)
        end_us = self._parse_time_to_microseconds(end_time)

        services_to_query = [service]
        if include_dependencies and service in self.DEPENDENCY_MAP:
            services_to_query.extend(self.DEPENDENCY_MAP[service])

        seen_spans: set[tuple[str, str]] = set()
        all_spans: list[dict[str, Any]] = []

        for svc in services_to_query:
            try:
                traces = await self._fetch_service_traces(svc, start_us, end_us, limit)
                for trace in traces:
                    parsed_spans = self._parse_trace_spans(trace, svc)
                    for span in parsed_spans:
                        key = (span["trace_id"], span["span_id"])
                        if key not in seen_spans:
                            seen_spans.add(key)
                            all_spans.append(span)
            except Exception as exc:
                logger.debug("Jaeger trace collection failed for service=%s: %s", svc, exc)
                continue

        all_spans.sort(key=lambda s: s.get("timestamp", ""))
        return all_spans

    async def _fetch_service_traces(
        self,
        service: str,
        start_us: int,
        end_us: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fetch raw traces for a single service from Jaeger API."""
        params = {
            "service": service,
            "start": str(start_us),
            "end": str(end_us),
            "limit": limit,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/traces",
                params=params,
            )
            if response.status_code != 200:
                logger.warning(
                    "Jaeger query returned status %d for service %s",
                    response.status_code,
                    service,
                )
                return []
            data = response.json()
            return data.get("data", [])

    def _parse_trace_spans(
        self,
        trace: dict[str, Any],
        default_service: str,
    ) -> list[dict[str, Any]]:
        """Parse spans from a single trace object."""
        spans: list[dict[str, Any]] = []
        trace_id = trace.get("traceID", "unknown")
        processes = trace.get("processes", {})

        for span in trace.get("spans", []):
            span_id = span.get("spanID", "unknown")
            operation = span.get("operationName", "unknown")
            start_us = span.get("startTime", 0)
            duration_us = span.get("duration", 0)
            duration_ms = round(duration_us / 1000.0, 3)

            # Discover accurate service name from Jaeger process metadata
            proc_id = span.get("processID", "")
            span_service = processes.get(proc_id, {}).get("serviceName", default_service)

            try:
                ts = datetime.fromtimestamp(start_us / 1_000_000, tz=timezone.utc)
                ts_str = ts.isoformat()
            except (ValueError, TypeError, OSError):
                ts_str = datetime.now(timezone.utc).isoformat()

            tags = {t.get("key"): t.get("value") for t in span.get("tags", []) if "key" in t}

            # Determine parent span ID if present in references
            parent_span_id = None
            for ref in span.get("references", []):
                if ref.get("refType") == "CHILD_OF":
                    parent_span_id = ref.get("spanID")
                    break

            # Determine span status
            has_error = self._span_has_error(span)
            status = "error" if has_error else "ok"

            spans.append({
                "source": "jaeger",
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "service": span_service,
                "operation": operation,
                "duration_ms": duration_ms,
                "status": status,
                "timestamp": ts_str,
                "tags": tags,
            })

        return spans

    @staticmethod
    def _span_has_error(span: dict[str, Any]) -> bool:
        """Check if a span indicates an error."""
        for tag in span.get("tags", []):
            if tag.get("key") == "error" and tag.get("value") is True:
                return True
            if (
                tag.get("key") == "otel.status_code"
                and str(tag.get("value")).upper() == "ERROR"
            ):
                return True
            if tag.get("key") == "http.status_code":
                try:
                    if int(tag.get("value", 0)) >= 400:
                        return True
                except (ValueError, TypeError):
                    pass
        return False

    @staticmethod
    def _extract_error_message(span: dict[str, Any]) -> str | None:
        """Extract error details from span logs or tags."""
        for tag in span.get("tags", []):
            if tag.get("key") in ("error.message", "exception.message"):
                return str(tag.get("value"))
        for log_entry in span.get("logs", []):
            for field in log_entry.get("fields", []):
                if field.get("key") in ("message", "error.object", "event"):
                    return str(field.get("value"))
        return None

    # ----- Backward compatibility helpers -----

    def _parse_response(
        self,
        data: dict[str, Any],
        service: str,
    ) -> list[NormalizedEvent]:
        """Parse Jaeger traces response into normalized events (backward compat)."""
        events: list[NormalizedEvent] = []
        traces = data.get("data", [])

        for trace in traces:
            trace_id = trace.get("traceID", "unknown")
            spans = trace.get("spans", [])

            for span in spans:
                span_id = span.get("spanID", "unknown")
                operation = span.get("operationName", "unknown")
                start_us = span.get("startTime", 0)
                duration_us = span.get("duration", 0)

                try:
                    timestamp = datetime.fromtimestamp(start_us / 1_000_000, tz=timezone.utc)
                except (ValueError, TypeError, OSError):
                    continue

                has_error = self._span_has_error(span)
                severity = "error" if has_error else "info"
                duration_ms = duration_us / 1_000

                content = (
                    f"Span {operation} "
                    f"duration={duration_ms:.1f}ms "
                    f"trace={trace_id}"
                )

                if has_error:
                    error_msg = self._extract_error_message(span)
                    if error_msg:
                        content += f" error={error_msg}"

                events.append(
                    NormalizedEvent(
                        timestamp=timestamp,
                        source="jaeger",
                        service=service,
                        event_type="trace",
                        severity=severity,
                        content=content,
                        metadata={
                            "trace_id": trace_id,
                            "span_id": span_id,
                            "operation": operation,
                            "duration_us": duration_us,
                            "duration_ms": duration_ms,
                            "tags": {
                                t["key"]: t.get("value")
                                for t in span.get("tags", [])
                            },
                        },
                    )
                )

        return events

    async def collect(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[NormalizedEvent]:
        """Collect traces and return them as NormalizedEvent instances."""
        structured_spans = await self.get_traces(
            service=service,
            start_time=start_time,
            end_time=end_time,
            include_dependencies=False,
        )
        events: list[NormalizedEvent] = []

        for span in structured_spans:
            try:
                dt = datetime.fromisoformat(span["timestamp"].replace("Z", "+00:00"))
            except Exception:
                dt = datetime.now(timezone.utc)

            has_error = span.get("status") == "error"
            severity = "error" if has_error else "info"
            content = (
                f"Span {span['operation']} "
                f"duration={span['duration_ms']:.1f}ms "
                f"trace={span['trace_id']}"
            )
            if has_error:
                content += " status=error"

            events.append(
                NormalizedEvent(
                    timestamp=dt,
                    source="jaeger",
                    service=span.get("service", service),
                    event_type="trace",
                    severity=severity,
                    content=content,
                    metadata={
                        "trace_id": span["trace_id"],
                        "span_id": span["span_id"],
                        "operation": span["operation"],
                        "duration_ms": span["duration_ms"],
                        "tags": span.get("tags", {}),
                    },
                )
            )

        return events

    async def get_trace(self, trace_id: str) -> dict[str, Any]:
        """Retrieve a single trace by ID."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/traces/{trace_id}",
            )
            response.raise_for_status()
            return response.json()

    async def health_check(self) -> bool:
        """Check if Jaeger is reachable."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/api/services")
                return response.status_code == 200
        except Exception:
            return False
