"""Prometheus metrics collector for incident evidence collection.

Retrieves request rate, error rate, latency, CPU usage, and memory usage
metrics for a service and time window, returning structured metric records.
"""

from __future__ import annotations

import logging
import math
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


class PrometheusCollector(BaseCollector):
    """Collector for Prometheus metrics."""

    METRIC_QUERIES: dict[str, list[str]] = {
        "request_rate": [
            'sum(rate(app_http_request_count_total{{service_name="{service}"}}[1m]))',
            'sum(rate(http_requests_total{{service="{service}"}}[1m]))',
            'sum(rate(app_http_request_count_total[1m]))',
        ],
        "error_rate": [
            'sum(rate(app_http_error_count_total{{service_name="{service}"}}[1m]))',
            'sum(rate(app_http_request_count_total{{service_name="{service}",status=~"5.."}}[1m]))',
            'sum(rate(app_http_error_count_total[1m]))',
        ],
        "latency": [
            'histogram_quantile(0.95, sum by (le) (rate(app_http_request_duration_seconds_bucket{{service_name="{service}"}}[1m])))',
            'sum(rate(app_http_request_duration_seconds_sum{{service_name="{service}"}}[1m])) / sum(rate(app_http_request_duration_seconds_count{{service_name="{service}"}}[1m]))',
            'histogram_quantile(0.95, sum by (le) (rate(app_http_request_duration_seconds_bucket[1m])))',
        ],
        "cpu_usage": [
            'sum(rate(container_cpu_usage_seconds_total{{container_label_com_docker_compose_service="{service}"}}[1m]))',
            'sum(rate(container_cpu_usage_seconds_total{{name=~".*{service}.*"}}[1m]))',
            'sum(rate(container_cpu_usage_seconds_total{{job="docker-metrics-exporter",container_label_com_docker_compose_service="{service}"}}[1m]))',
        ],
        "memory_usage": [
            'max(container_memory_working_set_bytes{{container_label_com_docker_compose_service="{service}"}})',
            'max(container_memory_working_set_bytes{{name=~".*{service}.*"}})',
            'max(container_memory_working_set_bytes{{job="docker-metrics-exporter",container_label_com_docker_compose_service="{service}"}})',
        ],
        "checkout_errors": [
            'sum(rate(ecommerce_checkout_error_count_total{{service_name="{service}"}}[1m]))',
        ],
        "payment_timeouts": [
            'sum(rate(ecommerce_payment_timeout_count_total{{service_name="{service}"}}[1m]))',
        ],
        "db_query_latency": [
            'histogram_quantile(0.95, sum by (le) (rate(ecommerce_db_query_duration_seconds_bucket{{service_name="{service}"}}[1m])))',
        ],
    }

    # Backward compatibility map
    DEFAULT_QUERIES = {
        "request_rate": (
            'sum(rate(app_http_request_count_total{{service_name="{service}"}}[1m]))'
        ),
        "error_rate": (
            'sum(rate(app_http_error_count_total{{service_name="{service}"}}[1m]))'
        ),
        "request_latency": (
            'histogram_quantile(0.95, sum by (le) (rate('
            'app_http_request_duration_seconds_bucket{{service_name="{service}"}}[1m])))'
        ),
        "cpu_usage": (
            'sum(rate(container_cpu_usage_seconds_total'
            '{{container_label_com_docker_compose_service="{service}"}}[1m]))'
        ),
        "memory_usage": (
            'max(container_memory_working_set_bytes'
            '{{container_label_com_docker_compose_service="{service}"}})'
        ),
        "checkout_errors": (
            'sum(rate(ecommerce_checkout_error_count_total{{service_name="{service}"}}[1m]))'
        ),
        "payment_timeouts": (
            'sum(rate(ecommerce_payment_timeout_count_total{{service_name="{service}"}}[1m]))'
        ),
        "db_query_latency": (
            'histogram_quantile(0.95, sum by (le) (rate('
            'ecommerce_db_query_duration_seconds_bucket{{service_name="{service}"}}[1m])))'
        ),
    }

    def __init__(self, base_url: str | None = None, timeout: float = 10.0) -> None:
        if not base_url:
            base_url = get_settings().PROMETHEUS_URL
        super().__init__(base_url=base_url, timeout=timeout)

    @staticmethod
    def _parse_time(dt_input: datetime | str) -> datetime:
        """Parse datetime or ISO string to UTC datetime."""
        if isinstance(dt_input, str):
            clean_str = dt_input.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)
        else:
            dt = dt_input

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    @staticmethod
    def _calculate_step(start_dt: datetime, end_dt: datetime) -> str:
        """Compute an appropriate query step interval based on time window."""
        delta_sec = max(1.0, (end_dt - start_dt).total_seconds())
        if delta_sec <= 120:
            return "5s"
        elif delta_sec <= 600:
            return "10s"
        elif delta_sec <= 3600:
            return "30s"
        return "60s"

    async def get_metrics(
        self,
        service: str,
        start_time: datetime | str,
        end_time: datetime | str,
        step: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve structured metric records for the incident time window.

        At minimum supports:
            - request rate
            - error rate
            - latency
            - CPU usage
            - memory usage

        Returns a list of dicts with keys:
            - source: "prometheus"
            - metric_name: metric identifier (e.g. "cpu_usage")
            - service: service name
            - timestamp: ISO-8601 string
            - value: numeric metric value
            - labels: metric label dict
        """
        start_dt = self._parse_time(start_time)
        end_dt = self._parse_time(end_time)
        step_val = step or self._calculate_step(start_dt, end_dt)

        all_metric_records: list[dict[str, Any]] = []

        for metric_name, query_templates in self.METRIC_QUERIES.items():
            records = await self._query_metric_with_fallbacks(
                metric_name, query_templates, service, start_dt, end_dt, step_val
            )
            all_metric_records.extend(records)

        all_metric_records.sort(key=lambda r: (r.get("timestamp", ""), r.get("metric_name", "")))
        return all_metric_records

    async def _query_metric_with_fallbacks(
        self,
        metric_name: str,
        query_templates: list[str],
        service: str,
        start_dt: datetime,
        end_dt: datetime,
        step: str,
    ) -> list[dict[str, Any]]:
        """Try primary query and fallbacks until records are found or list exhausted."""
        for tmpl in query_templates:
            query = tmpl.format(service=service)
            try:
                res = await self.query_range(query, start_dt, end_dt, step)
                records = self._parse_prometheus_matrix(res, metric_name, service)
                if records:
                    return records
            except Exception as exc:
                logger.debug("Prometheus query failed metric=%s query=%s: %s", metric_name, query, exc)
                continue
        return []

    def _parse_prometheus_matrix(
        self,
        response: dict[str, Any],
        metric_name: str,
        service: str,
    ) -> list[dict[str, Any]]:
        """Parse Prometheus query_range matrix result into structured records."""
        records: list[dict[str, Any]] = []
        if response.get("status") != "success":
            return records

        results = response.get("data", {}).get("result", [])
        for series in results:
            metric_labels = series.get("metric", {})
            values = series.get("values", [])

            # Handle instant query single value format
            if not values and series.get("value"):
                values = [series.get("value")]

            for val_pair in values:
                if not val_pair or len(val_pair) < 2:
                    continue
                try:
                    ts_epoch = float(val_pair[0])
                    val = float(val_pair[1])
                    if not math.isfinite(val):
                        continue
                    ts = datetime.fromtimestamp(ts_epoch, tz=timezone.utc)
                except (ValueError, TypeError, OSError):
                    continue

                records.append({
                    "source": "prometheus",
                    "metric_name": metric_name,
                    "service": service,
                    "timestamp": ts.isoformat(),
                    "value": round(val, 4),
                    "labels": metric_labels,
                })

        return records

    async def query_prometheus(
        self,
        query: str,
        time: datetime | None = None,
    ) -> dict[str, Any]:
        """Execute an instant query against Prometheus."""
        params: dict[str, Any] = {"query": query}
        if time is not None:
            params["time"] = time.isoformat()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/query",
                params=params,
            )
            response.raise_for_status()
            return response.json()

    async def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "60s",
    ) -> dict[str, Any]:
        """Execute a range query against Prometheus."""
        params = {
            "query": query,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "step": step,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/query_range",
                params=params,
            )
            response.raise_for_status()
            return response.json()

    async def health_check(self) -> bool:
        """Check if Prometheus is reachable."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/-/healthy")
                if response.status_code == 200:
                    return True
        except Exception:
            pass

        # Try fallback URL if container hostname is unreachable locally
        fallback_url = (
            "http://localhost:9090"
            if "prometheus" in self.base_url
            else "http://prometheus:9090"
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{fallback_url}/-/healthy")
                if response.status_code == 200:
                    self.base_url = fallback_url
                    return True
        except Exception:
            pass

        return False

    # ----- Backward compatibility helpers -----

    async def collect(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[NormalizedEvent]:
        """Collect all configured metrics for a service as NormalizedEvents."""
        events: list[NormalizedEvent] = []

        for metric_name, query_template in self.DEFAULT_QUERIES.items():
            query = query_template.format(service=service)
            try:
                results = await self.query_range(
                    query=query,
                    start=start_time,
                    end=end_time,
                    step="5s",
                )
                events.extend(
                    self._to_events(results, service, metric_name)
                )
            except Exception as exc:
                logger.warning(
                    "Prometheus query failed metric=%s: %s",
                    metric_name,
                    exc,
                )

        return events

    def _to_events(
        self,
        response: dict[str, Any],
        service: str,
        metric_name: str,
    ) -> list[NormalizedEvent]:
        """Convert a Prometheus API response to normalized events."""
        events: list[NormalizedEvent] = []
        if response.get("status") != "success":
            return events

        results = response.get("data", {}).get("result", [])
        for result in results:
            metric_labels = result.get("metric", {})
            values = result.get("values", [])

            if not values:
                value_pair = result.get("value")
                if value_pair:
                    values = [value_pair]

            for ts, value in values:
                try:
                    float_value = float(value)
                except (ValueError, TypeError):
                    continue
                if not math.isfinite(float_value):
                    continue

                severity = self._determine_severity(metric_name, float_value)

                events.append(
                    NormalizedEvent(
                        timestamp=datetime.fromtimestamp(float(ts), tz=timezone.utc),
                        source="prometheus",
                        service=service,
                        event_type=metric_name,
                        severity=severity,
                        content=f"{metric_name} = {float_value:.4f}",
                        metadata={
                            "value": float_value,
                            "labels": metric_labels,
                        },
                    )
                )

        return events

    @staticmethod
    def _determine_severity(metric_name: str, value: float) -> str:
        """Determine severity based on metric type and value thresholds."""
        thresholds: dict[str, dict[str, float]] = {
            "cpu_usage": {"warning": 0.7, "error": 0.9, "critical": 0.95},
            "memory_usage": {
                "warning": 0.7e9,
                "error": 0.9e9,
                "critical": 0.95e9,
            },
            "error_rate": {"warning": 0.01, "error": 0.05, "critical": 0.1},
            "request_latency": {
                "warning": 1.0,
                "error": 3.0,
                "critical": 5.0,
            },
            "latency": {
                "warning": 1.0,
                "error": 3.0,
                "critical": 5.0,
            },
        }

        levels = thresholds.get(metric_name, {})
        if levels.get("critical") and value >= levels["critical"]:
            return "critical"
        if levels.get("error") and value >= levels["error"]:
            return "error"
        if levels.get("warning") and value >= levels["warning"]:
            return "warning"
        return "info"

    async def get_service_cpu(self, service: str) -> dict[str, Any]:
        query = self.DEFAULT_QUERIES["cpu_usage"].format(service=service)
        return await self.query_prometheus(query)

    async def get_service_memory(self, service: str) -> dict[str, Any]:
        query = self.DEFAULT_QUERIES["memory_usage"].format(service=service)
        return await self.query_prometheus(query)

    async def get_request_rate(self, service: str) -> dict[str, Any]:
        query = self.DEFAULT_QUERIES["request_rate"].format(service=service)
        return await self.query_prometheus(query)

    async def get_error_rate(self, service: str) -> dict[str, Any]:
        query = self.DEFAULT_QUERIES["error_rate"].format(service=service)
        return await self.query_prometheus(query)

    async def query_scalar(
        self, query: str, default: float | None = None
    ) -> float | None:
        try:
            res = await self.query_prometheus(query)
            if res.get("status") == "success":
                results = res.get("data", {}).get("result", [])
                if results and len(results) > 0:
                    val_pair = results[0].get("value")
                    if val_pair and len(val_pair) > 1:
                        val = float(val_pair[1])
                        if val == val:
                            return val
        except Exception as exc:
            logger.debug("Prometheus query_scalar failed query=%s: %s", query, exc)
        return default

    async def get_discovered_services(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/label/service_name/values"
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "success":
                        values = data.get("data", [])
                        if values:
                            return sorted(values)
        except Exception as exc:
            logger.debug("Prometheus get_discovered_services failed: %s", exc)
        return []

    async def query_range_values(
        self, query: str, duration_seconds: int = 900, step: str = "60s"
    ) -> list[float]:
        """Execute a range query against Prometheus and return numeric values for sparklines."""
        try:
            end_dt = datetime.now(timezone.utc)
            start_dt = datetime.fromtimestamp(
                end_dt.timestamp() - duration_seconds, tz=timezone.utc
            )
            res = await self.query_range(query, start=start_dt, end=end_dt, step=step)
            if res.get("status") == "success":
                results = res.get("data", {}).get("result", [])
                if results and len(results) > 0:
                    raw_values = results[0].get("values", [])
                    out: list[float] = []
                    for pair in raw_values:
                        try:
                            val = float(pair[1])
                            if val == val:
                                out.append(round(val, 2))
                        except (ValueError, TypeError):
                            continue
                    return out
        except Exception as exc:
            logger.debug("Prometheus query_range_values failed: %s", exc)
        return []

    async def get_prometheus_alert_rules(self) -> list[dict[str, Any]]:
        """Fetch alert rules and active alerts from Prometheus API."""
        rules: list[dict[str, Any]] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.get(f"{self.base_url}/api/v1/rules")
                if res.status_code == 200:
                    data = res.json()
                    if data.get("status") == "success":
                        groups = data.get("data", {}).get("groups", [])
                        for group in groups:
                            for r in group.get("rules", []):
                                if r.get("type") == "alerting":
                                    rules.append(
                                        {
                                            "name": r.get("name", "AlertRule"),
                                            "query": r.get("query", ""),
                                            "severity": r.get("labels", {})
                                            .get("severity", "info")
                                            .upper(),
                                            "status": r.get("state", "ok").upper(),
                                        }
                                    )
        except Exception as exc:
            logger.debug("Prometheus get_prometheus_alert_rules failed: %s", exc)
        return rules

