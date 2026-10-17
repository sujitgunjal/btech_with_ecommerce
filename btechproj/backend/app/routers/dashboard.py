"""Dashboard overview and microservices telemetry endpoints."""

import logging
import os

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from datetime import datetime, timezone

from ..collectors.prometheus import PrometheusCollector
from ..config import get_settings
from ..database import get_db
from ..models.incident import Incident
from ..schemas.dashboard import (
    DashboardOverviewResponse,
    MonitoringMetricItem,
    MonitoringResponse,
    PrometheusAlertRuleItem,
    ServiceHealthItem,
    ServicesListResponse,
)
from ..service_metrics import WINDOW_MINUTES, summarize_service_traffic

logger = logging.getLogger("incident-backend")

router = APIRouter()

# Thresholds configuration for service health evaluation
HEALTH_THRESHOLDS = {
    "latency_degraded_ms": 300.0,
    "latency_critical_ms": 800.0,
    "error_rate_degraded": 1.0,  # 1%
    "error_rate_critical": 5.0,  # 5%
}

DEFAULT_MONITORED_SERVICES = [
    "user-service",
    "product-service",
    "order-service",
]


# Host ports for services that are not on the AI project's Docker network.
# The shop publishes 8100 and 8101; the original services also have host ports.
HOST_HEALTH_URLS = {
    "user-service": "http://host.docker.internal:8001/health",
    "product-service": "http://host.docker.internal:8002/health",
    "order-service": "http://host.docker.internal:8003/health",
    "ecommerce-shop-api": "http://host.docker.internal:8100/health",
    "ecommerce-payment-gateway": "http://host.docker.internal:8101/health",
}


async def is_service_reachable(service_name: str) -> bool:
    """Check health directly, then fall back to a live Prometheus series.

    The shop services run on another Compose network, so their container DNS
    names do not resolve here. A missing name is not the same as a stopped
    process when Prometheus is still receiving that service's metrics.
    """
    if await _probe_health(service_name):
        return True
    return await _prometheus_has_service(service_name)


async def _probe_health(service_name: str) -> bool:
    urls = []
    host_url = HOST_HEALTH_URLS.get(service_name)
    if host_url:
        urls.append(host_url)
    urls.append(f"http://{service_name}:8000/health")

    try:
        async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
            for url in urls:
                try:
                    res = await client.get(url)
                    if res.status_code == 200:
                        return True
                except Exception as exc:
                    logger.debug(
                        "Health check probe failed for %s at %s: %s",
                        service_name,
                        url,
                        exc,
                    )
                    continue
    except Exception as exc:
        logger.warning(
            "Health check client error for %s: %s", service_name, exc
        )
    return False


async def _prometheus_has_service(service_name: str) -> bool:
    settings = get_settings()
    collector = PrometheusCollector(settings.PROMETHEUS_URL, settings.COLLECTOR_TIMEOUT)
    for metric in (
        "http_server_duration_milliseconds_count",
        "app_http_request_count_total",
    ):
        count = await collector.query_scalar(
            f'count({metric}{{service_name="{service_name}"}})'
        )
        if count is not None and count > 0:
            return True
    return False


def determine_service_status(
    error_rate: float | None, latency_ms: float | None, is_up: bool = True
) -> str:
    """Determine service status based on reachability and performance thresholds."""
    if not is_up:
        return "down"
    observed_error = error_rate if error_rate is not None else 0.0
    observed_latency = latency_ms if latency_ms is not None else 0.0
    if (
        observed_error >= HEALTH_THRESHOLDS["error_rate_critical"]
        or observed_latency >= HEALTH_THRESHOLDS["latency_critical_ms"]
    ):
        return "critical"
    if (
        observed_error >= HEALTH_THRESHOLDS["error_rate_degraded"]
        or observed_latency >= HEALTH_THRESHOLDS["latency_degraded_ms"]
    ):
        return "degraded"
    return "healthy"


def calculate_system_health(
    error_rate: float,
    average_latency_ms: float,
    healthy_services: int,
    total_services: int,
) -> int:
    """Calculate an explainable 0-100 system health score.

    Formula:
    Base: 100
    - Error rate penalty: 2.5 points per 1% error rate
    - Latency penalty: 1 point per 40ms above 100ms baseline
    - Service degradation penalty: 10 points per non-healthy service
    Result is clamped to range [0, 100].
    """
    error_penalty = min(30.0, error_rate * 2.5)
    latency_penalty = min(20.0, max(0.0, (average_latency_ms - 100.0) / 40.0))
    unhealthy_count = max(0, total_services - healthy_services)
    service_penalty = min(30.0, unhealthy_count * 10.0)

    score = 100.0 - error_penalty - latency_penalty - service_penalty
    return max(0, min(100, int(round(score))))


CUSTOMER_TARGET_FILTER = (
    'http_target!~"/health|/health/ready|/ops.*|/internal.*|/docs|/redoc|/openapi.json"'
)


async def _service_card_metrics(collector, service_name: str) -> dict[str, float | None]:
    """Prefer the app HTTP counters, then the FastAPI duration histogram."""
    window = f"{WINDOW_MINUTES}m"
    app_requests = await collector.query_scalar(
        f'sum(increase(app_http_request_count_total{{service_name="{service_name}"}}[{window}]))'
    )
    if app_requests is not None:
        return summarize_service_traffic(
            telemetry_present=True,
            request_count=app_requests,
            error_count=await collector.query_scalar(
                f'sum(increase(app_http_error_count_total{{service_name="{service_name}"}}[{window}]))'
            ),
            duration_total=await collector.query_scalar(
                f'sum(increase(app_http_request_duration_seconds_sum{{service_name="{service_name}"}}[{window}]))'
            ),
            duration_unit="s",
        )

    present = await collector.query_scalar(
        f'count(http_server_duration_milliseconds_count{{service_name="{service_name}"}})'
    )
    selector = f'service_name="{service_name}",{CUSTOMER_TARGET_FILTER}'
    return summarize_service_traffic(
        telemetry_present=present is not None and present > 0,
        request_count=await collector.query_scalar(
            f"sum(increase(http_server_duration_milliseconds_count{{{selector}}}[{window}]))"
        ),
        error_count=await collector.query_scalar(
            "sum(increase(http_server_duration_milliseconds_count{"
            f'{selector},http_status_code=~"5.."}}[{window}]))'
        ),
        duration_total=await collector.query_scalar(
            f"sum(increase(http_server_duration_milliseconds_sum{{{selector}}}[{window}]))"
        ),
        duration_unit="ms",
    )


@router.get(
    "/services",
    response_model=ServicesListResponse,
    summary="Get Microservices Catalog Health Telemetry",
)
async def get_services_telemetry():
    """Fetch health telemetry and metrics for registered microservices (Single Source of Truth)."""
    settings = get_settings()
    collector = PrometheusCollector(
        settings.PROMETHEUS_URL, settings.COLLECTOR_TIMEOUT
    )

    discovered = await collector.get_discovered_services()
    monitored_services = (
        discovered if len(discovered) > 0 else DEFAULT_MONITORED_SERVICES
    )

    services: list[ServiceHealthItem] = []

    for service_name in monitored_services:
        is_up = await is_service_reachable(service_name)
        metrics = await _service_card_metrics(collector, service_name)
        status = determine_service_status(
            metrics["error_rate"],
            metrics["average_latency_ms"],
            is_up=is_up,
        )

        services.append(
            ServiceHealthItem(
                name=service_name,
                status=status,
                requests_per_minute=metrics["requests_per_minute"],
                average_latency_ms=metrics["average_latency_ms"],
                error_rate=metrics["error_rate"],
            )
        )

    logger.info(
        "[DATA_SOURCE: LIVE] Fetched live status for %d services: %s",
        len(services),
        [(s.name, s.status) for s in services],
    )
    return ServicesListResponse(services=services)


@router.get(
    "/dashboard/overview",
    response_model=DashboardOverviewResponse,
    summary="Get System Overview Metrics",
)
async def get_dashboard_overview(db: Session = Depends(get_db)):
    """Fetch high-level infrastructure telemetry & system overview metrics (Unified Source of Truth)."""
    # 1. Query PostgreSQL for active (unresolved) incidents count
    active_incidents = (
        db.query(Incident)
        .filter(Incident.status != "resolved")
        .count()
    )

    # 2. Shared single source of truth for microservices telemetry
    services_res = await get_services_telemetry()
    services_list = services_res.services

    # Compute healthy and total counts dynamically directly from services_list
    healthy_services_count = sum(
        1 for s in services_list if s.status == "healthy"
    )
    total_services_count = len(services_list)

    total_rpm = sum((s.requests_per_minute or 0.0) for s in services_list)
    active_latencies = [
        s.average_latency_ms
        for s in services_list
        if s.average_latency_ms is not None and (s.requests_per_minute or 0.0) > 0
    ]
    overall_latency = (
        sum(active_latencies) / len(active_latencies)
        if active_latencies
        else 0.0
    )
    weighted_errors = [
        (s.error_rate, s.requests_per_minute)
        for s in services_list
        if s.error_rate is not None and (s.requests_per_minute or 0.0) > 0
    ]
    overall_err_rate = (
        sum(rate * rpm for rate, rpm in weighted_errors) / sum(rpm for _, rpm in weighted_errors)
        if weighted_errors
        else 0.0
    )

    system_health_score = calculate_system_health(
        error_rate=overall_err_rate,
        average_latency_ms=overall_latency,
        healthy_services=healthy_services_count,
        total_services=total_services_count,
    )

    avg_lat = round(overall_latency, 1)
    rpm_val = round(total_rpm, 1)

    return DashboardOverviewResponse(
        system_health=system_health_score,
        active_incidents=active_incidents,
        error_rate=round(overall_err_rate, 2),
        average_latency_ms=avg_lat,
        average_latency=avg_lat,
        healthy_services=healthy_services_count,
        total_services=total_services_count,
        requests_per_minute=rpm_val,
        request_rate=rpm_val,
        services=services_list,
    )


def _get_demo_overview(active_incidents: int) -> DashboardOverviewResponse:
    services = [ServiceHealthItem(**item) for item in FALLBACK_SERVICES]
    return DashboardOverviewResponse(
        system_health=92,
        active_incidents=active_incidents,
        error_rate=7.2,
        average_latency_ms=284.0,
        average_latency=284.0,
        healthy_services=2,
        total_services=3,
        requests_per_minute=102400.0,
        request_rate=102400.0,
        services=services,
    )


def _get_fallback_overview(active_incidents: int) -> DashboardOverviewResponse:
    services = [ServiceHealthItem(**item) for item in FALLBACK_SERVICES]
    return DashboardOverviewResponse(
        system_health=75,
        active_incidents=active_incidents,
        error_rate=0.0,
        average_latency_ms=10.0,
        average_latency=10.0,
        healthy_services=3,
        total_services=3,
        requests_per_minute=12.0,
        request_rate=12.0,
        services=services,
    )


@router.get(
    "/monitoring",
    response_model=MonitoringResponse,
    summary="Get Real Live Observability Telemetry & Alert Rules",
)
async def get_monitoring_data():
    """Fetch live cluster telemetry, sparkline time-series, and alert rules from Prometheus."""
    settings = get_settings()
    collector = PrometheusCollector(
        settings.PROMETHEUS_URL, settings.COLLECTOR_TIMEOUT
    )

    is_up = await collector.health_check()
    now_str = datetime.now(timezone.utc).isoformat()

    if not is_up:
        logger.warning(
            "[DATA_SOURCE: ERROR] Prometheus at %s is unreachable for GET /monitoring.",
            settings.PROMETHEUS_URL,
        )
        return MonitoringResponse(
            prometheus_up=False,
            cpu_utilization=MonitoringMetricItem(
                name="Cluster CPU Utilization",
                display_value="Not available",
                unit="%",
                is_available=False,
            ),
            memory_usage=MonitoringMetricItem(
                name="Cluster RAM Usage",
                display_value="Not available",
                unit="%",
                is_available=False,
            ),
            network_throughput=MonitoringMetricItem(
                name="Ingress Network Throughput",
                display_value="Not available",
                unit="KB/s",
                is_available=False,
            ),
            alert_rules=[],
            timestamp=now_str,
        )

    # PromQL Instant Queries
    cpu_query = "sum(rate(container_cpu_usage_seconds_total[5m])) * 100"
    mem_query = "(sum(container_memory_working_set_bytes) / 8138678272.0) * 100"
    net_query = "sum(rate(container_network_receive_bytes_total[5m])) / 1024.0"

    cpu_val = await collector.query_scalar(cpu_query)
    mem_val = await collector.query_scalar(mem_query)
    net_val = await collector.query_scalar(net_query)

    # PromQL Range Queries for Sparklines (15m window)
    cpu_spark = await collector.query_range_values(cpu_query, duration_seconds=900, step="60s")
    mem_spark = await collector.query_range_values(mem_query, duration_seconds=900, step="60s")
    net_spark = await collector.query_range_values(net_query, duration_seconds=900, step="60s")

    # Alert Rules from Prometheus
    raw_rules = await collector.get_prometheus_alert_rules()
    alert_rules = [PrometheusAlertRuleItem(**r) for r in raw_rules]

    # Format metric display values
    cpu_display = f"{round(cpu_val, 1)}%" if cpu_val is not None else "Not available"
    mem_display = f"{round(mem_val, 1)}%" if mem_val is not None else "Not available"

    if net_val is None:
        net_display = "Not available"
        net_unit = "KB/s"
    elif net_val >= 1024 * 1024:
        net_display = f"{round(net_val / (1024 * 1024), 2)} GB/s"
        net_unit = "GB/s"
    elif net_val >= 1024:
        net_display = f"{round(net_val / 1024, 2)} MB/s"
        net_unit = "MB/s"
    else:
        net_display = f"{round(net_val, 1)} KB/s"
        net_unit = "KB/s"

    return MonitoringResponse(
        prometheus_up=True,
        cpu_utilization=MonitoringMetricItem(
            name="Cluster CPU Utilization",
            display_value=cpu_display,
            numeric_value=round(cpu_val, 1) if cpu_val is not None else None,
            unit="%",
            sparkline=cpu_spark,
            is_available=cpu_val is not None,
        ),
        memory_usage=MonitoringMetricItem(
            name="Cluster RAM Usage",
            display_value=mem_display,
            numeric_value=round(mem_val, 1) if mem_val is not None else None,
            unit="%",
            sparkline=mem_spark,
            is_available=mem_val is not None,
        ),
        network_throughput=MonitoringMetricItem(
            name="Ingress Network Throughput",
            display_value=net_display,
            numeric_value=round(net_val, 1) if net_val is not None else None,
            unit=net_unit,
            sparkline=net_spark,
            is_available=net_val is not None,
        ),
        alert_rules=alert_rules,
        timestamp=now_str,
    )
