"""Loki log collector for incident evidence collection.

Retrieves logs from Grafana Loki for a given service and time window,
returning structured log records with timestamp, service, level, message,
and labels.
"""

from __future__ import annotations

import json
import logging
import re
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


class LokiCollector(BaseCollector):
    """Collector for retrieving structured log records from Loki."""

    def __init__(self, base_url: str | None = None, timeout: float = 10.0) -> None:
        if not base_url:
            base_url = get_settings().LOKI_URL
        super().__init__(base_url=base_url, timeout=timeout)

    @staticmethod
    def _parse_time_to_nanoseconds(dt_input: datetime | str) -> int:
        """Convert a datetime or ISO-8601 string to unix nanoseconds."""
        if isinstance(dt_input, str):
            clean_str = dt_input.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)
        else:
            dt = dt_input

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1_000_000_000)

    @staticmethod
    def _detect_severity(log_line: str, labels: dict[str, str] | None = None) -> str:
        """Detect log severity level from labels or log line content (lowercase)."""
        if labels:
            for key in ("level", "severity", "levelname"):
                if key in labels and labels[key]:
                    val = labels[key].lower()
                    if "crit" in val or "fatal" in val:
                        return "critical"
                    if "err" in val:
                        return "error"
                    if "warn" in val:
                        return "warning"
                    return val

        # Check for JSON log line
        trimmed = log_line.strip()
        if trimmed.startswith("{") and trimmed.endswith("}"):
            try:
                parsed = json.loads(trimmed)
                for key in ("level", "severity", "levelname", "log_level"):
                    if key in parsed and parsed[key]:
                        val = str(parsed[key]).lower()
                        if "crit" in val or "fatal" in val:
                            return "critical"
                        if "err" in val:
                            return "error"
                        if "warn" in val:
                            return "warning"
                        return val
            except (json.JSONDecodeError, TypeError):
                pass

        upper = log_line.upper()
        if "CRITICAL" in upper or "FATAL" in upper:
            return "critical"
        if "ERROR" in upper or "EXCEPTION" in upper:
            return "error"
        if "WARN" in upper:
            return "warning"
        return "info"

    async def get_logs(
        self,
        service: str,
        start_time: datetime | str,
        end_time: datetime | str,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Retrieve structured log records for a service and time window.

        Returns a list of dicts with keys:
            - source: "loki"
            - timestamp: ISO-8601 string
            - service: service name
            - level: severity string (e.g. INFO, ERROR)
            - message: log message text
            - labels: dictionary of Loki stream labels
        """
        start_ns = self._parse_time_to_nanoseconds(start_time)
        end_ns = self._parse_time_to_nanoseconds(end_time)

        # Primary query uses service_name label (standard OTel resource attribute)
        primary_query = f'{{service_name="{service}"}}'
        records = await self._query_loki(primary_query, start_ns, end_ns, limit, service)

        # If primary query returned no logs, try fallback container regex
        if not records:
            fallback_query = f'{{container=~".*{service}.*"}}'
            records = await self._query_loki(fallback_query, start_ns, end_ns, limit, service)

        records.sort(key=lambda r: r.get("timestamp", ""))
        return records

    async def _query_loki(
        self,
        query: str,
        start_ns: int,
        end_ns: int,
        limit: int,
        service: str,
    ) -> list[dict[str, Any]]:
        """Execute a range query against the Loki API."""
        params = {
            "query": query,
            "start": str(start_ns),
            "end": str(end_ns),
            "limit": limit,
            "direction": "forward",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/loki/api/v1/query_range",
                    params=params,
                )
                if response.status_code != 200:
                    logger.warning(
                        "Loki query returned status %d: %s",
                        response.status_code,
                        response.text[:200],
                    )
                    return []
                data = response.json()
        except Exception as exc:
            logger.warning("Loki collector query failed: %s", exc)
            return []

        return self._parse_structured_records(data, service)

    def _parse_structured_records(
        self,
        data: dict[str, Any],
        service: str,
    ) -> list[dict[str, Any]]:
        """Parse raw Loki query_range response into clean structured records."""
        records: list[dict[str, Any]] = []
        results = data.get("data", {}).get("result", [])

        for stream in results:
            labels = stream.get("stream", {})
            values = stream.get("values", [])

            for ts_ns, line in values:
                try:
                    ts = datetime.fromtimestamp(
                        int(ts_ns) / 1_000_000_000, tz=timezone.utc
                    )
                except (ValueError, TypeError, OSError):
                    continue

                severity_lower = self._detect_severity(line, labels)

                records.append({
                    "source": "loki",
                    "timestamp": ts.isoformat(),
                    "service": service,
                    "level": severity_lower.upper(),
                    "message": line,
                    "labels": labels,
                })

        return records

    def _parse_response(
        self,
        data: dict[str, Any],
        service: str,
    ) -> list[NormalizedEvent]:
        """Parse Loki query_range response into normalized events."""
        events: list[NormalizedEvent] = []
        results = data.get("data", {}).get("result", [])

        for stream in results:
            labels = stream.get("stream", {})
            values = stream.get("values", [])

            for ts_ns, line in values:
                try:
                    timestamp = datetime.fromtimestamp(
                        int(ts_ns) / 1_000_000_000, tz=timezone.utc
                    )
                except (ValueError, TypeError, OSError):
                    continue

                severity = self._detect_severity(line, labels)

                events.append(
                    NormalizedEvent(
                        timestamp=timestamp,
                        source="loki",
                        service=service,
                        event_type="log_entry",
                        severity=severity,
                        content=line,
                        metadata={"labels": labels},
                    )
                )

        return events

    # ----- Backward compatibility with BaseCollector & NormalizedEvent -----

    async def collect(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[NormalizedEvent]:
        """Collect logs and return them as NormalizedEvent instances."""
        start_ns = self._parse_time_to_nanoseconds(start_time)
        end_ns = self._parse_time_to_nanoseconds(end_time)
        query = f'{{service_name="{service}"}}'
        params = {
            "query": query,
            "start": str(start_ns),
            "end": str(end_ns),
            "limit": 100,
            "direction": "backward",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/loki/api/v1/query_range",
                    params=params,
                )
                response.raise_for_status()
                data = response.json()
                return self._parse_response(data, service)
        except Exception as exc:
            logger.warning("Loki collect failed: %s", exc)
            return []

    async def health_check(self) -> bool:
        """Check if Loki is reachable."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/ready")
                return response.status_code == 200
        except Exception:
            return False
