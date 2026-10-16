"""Unified Evidence Service for incident investigation.

Coordinates telemetry collection across Loki (logs), Prometheus (metrics),
and Jaeger (traces) for an incident time window and affected service.
Returns a unified, deterministic evidence payload ready for RAG and LLM reasoning.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

try:
    from app.collectors.jaeger_collector import JaegerCollector
    from app.collectors.loki_collector import LokiCollector
    from app.collectors.prometheus_collector import PrometheusCollector
    from app.config import get_settings
except ImportError:
    from backend.app.collectors.jaeger_collector import JaegerCollector
    from backend.app.collectors.loki_collector import LokiCollector
    from backend.app.collectors.prometheus_collector import PrometheusCollector
    from backend.app.config import get_settings

logger = logging.getLogger("incident-backend")


class EvidenceService:
    """Orchestrates telemetry collection and correlates evidence across all sources."""

    def __init__(
        self,
        loki_collector: Optional[LokiCollector] = None,
        prometheus_collector: Optional[PrometheusCollector] = None,
        jaeger_collector: Optional[JaegerCollector] = None,
    ) -> None:
        settings = get_settings()
        self.loki = loki_collector or LokiCollector(
            base_url=settings.LOKI_URL, timeout=settings.COLLECTOR_TIMEOUT
        )
        self.prometheus = prometheus_collector or PrometheusCollector(
            base_url=settings.PROMETHEUS_URL, timeout=settings.COLLECTOR_TIMEOUT
        )
        self.jaeger = jaeger_collector or JaegerCollector(
            base_url=settings.JAEGER_URL, timeout=settings.COLLECTOR_TIMEOUT
        )

    @staticmethod
    def _normalize_time(
        dt_input: datetime | str | None,
        default_ref: datetime | None = None,
        offset_minutes: int = 15,
    ) -> tuple[datetime, str]:
        """Convert datetime or ISO string to UTC datetime and standard ISO string."""
        if dt_input is None:
            if default_ref is not None:
                dt = default_ref + timedelta(minutes=offset_minutes)
            else:
                dt = datetime.now(timezone.utc)
        elif isinstance(dt_input, str):
            clean_str = dt_input.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)
        else:
            dt = dt_input

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        iso_str = dt.isoformat().replace("+00:00", "Z")
        return dt, iso_str

    async def get_incident_evidence(
        self,
        incident_id: str,
        service: str,
        start_time: datetime | str,
        end_time: datetime | str | None = None,
    ) -> dict[str, Any]:
        """Collect and correlate telemetry evidence for an incident.

        Args:
            incident_id: External or internal incident ID (e.g. "INC-001").
            service: Affected service name (e.g. "order-service").
            start_time: Start of incident window.
            end_time: End of incident window (defaults to start_time + 15m if omitted).

        Returns:
            Unified evidence dictionary:
            {
                "incident_id": "...",
                "service": "...",
                "time_window": {
                    "start": "...",
                    "end": "..."
                },
                "logs": [...],
                "metrics": [...],
                "traces": [...]
            }
        """
        start_dt, start_iso = self._normalize_time(start_time)
        end_dt, end_iso = self._normalize_time(
            end_time, default_ref=start_dt, offset_minutes=15
        )

        # Ensure valid time order
        if end_dt <= start_dt:
            end_dt = start_dt + timedelta(minutes=15)
            end_iso = end_dt.isoformat().replace("+00:00", "Z")

        logger.info(
            "Collecting unified evidence incident_id=%s service=%s window=[%s to %s]",
            incident_id,
            service,
            start_iso,
            end_iso,
        )

        # Collect concurrently across all three telemetry systems
        logs_res, metrics_res, traces_res = await asyncio.gather(
            self._fetch_logs(service, start_dt, end_dt),
            self._fetch_metrics(service, start_dt, end_dt),
            self._fetch_traces(service, start_dt, end_dt),
            return_exceptions=True,
        )

        logs = logs_res if isinstance(logs_res, list) else []
        metrics = metrics_res if isinstance(metrics_res, list) else []
        traces = traces_res if isinstance(traces_res, list) else []

        # Ensure source attribution on every item
        for item in logs:
            item["source"] = "loki"
        for item in metrics:
            item["source"] = "prometheus"
        for item in traces:
            item["source"] = "jaeger"

        # Deterministic sorting
        logs.sort(key=lambda x: x.get("timestamp", ""))
        metrics.sort(key=lambda x: (x.get("timestamp", ""), x.get("metric_name", "")))
        traces.sort(key=lambda x: (x.get("timestamp", ""), x.get("trace_id", ""), x.get("span_id", "")))

        from .correlation import correlation_notes

        correlations = correlation_notes([*logs, *metrics, *traces])

        logger.info(
            "Unified evidence collected incident_id=%s counts: logs=%d metrics=%d traces=%d",
            incident_id,
            len(logs),
            len(metrics),
            len(traces),
        )

        return {
            "incident_id": str(incident_id),
            "service": service,
            "time_window": {
                "start": start_iso,
                "end": end_iso,
            },
            "logs": logs,
            "metrics": metrics,
            "traces": traces,
            "correlations": correlations,
        }

    async def _fetch_logs(
        self, service: str, start_dt: datetime, end_dt: datetime
    ) -> list[dict[str, Any]]:
        """Fetch logs from Loki with graceful error handling."""
        try:
            return await self.loki.get_logs(service, start_dt, end_dt)
        except Exception as exc:
            logger.warning("Loki collection failed gracefully for %s: %s", service, exc)
            return []

    async def _fetch_metrics(
        self, service: str, start_dt: datetime, end_dt: datetime
    ) -> list[dict[str, Any]]:
        """Fetch metrics from Prometheus with graceful error handling."""
        try:
            return await self.prometheus.get_metrics(service, start_dt, end_dt)
        except Exception as exc:
            logger.warning("Prometheus collection failed gracefully for %s: %s", service, exc)
            return []

    async def _fetch_traces(
        self, service: str, start_dt: datetime, end_dt: datetime
    ) -> list[dict[str, Any]]:
        """Fetch traces from Jaeger with graceful error handling."""
        try:
            return await self.jaeger.get_traces(
                service, start_dt, end_dt, include_dependencies=True
            )
        except Exception as exc:
            logger.warning("Jaeger collection failed gracefully for %s: %s", service, exc)
            return []


# Top-level helper function
async def get_incident_evidence(
    incident_id: str,
    service: str,
    start_time: datetime | str,
    end_time: datetime | str | None = None,
    evidence_service: Optional[EvidenceService] = None,
) -> dict[str, Any]:
    """Retrieve correlated evidence across Loki, Prometheus, and Jaeger."""
    service_instance = evidence_service or EvidenceService()
    return await service_instance.get_incident_evidence(
        incident_id=incident_id,
        service=service,
        start_time=start_time,
        end_time=end_time,
    )
