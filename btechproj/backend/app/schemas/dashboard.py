"""Pydantic schemas for dashboard overview and microservices health endpoints."""

from pydantic import BaseModel, Field


class ServiceHealthItem(BaseModel):
    """Schema for individual service in GET /services list."""

    name: str = Field(..., description="Service identifier name")
    status: str = Field(
        ...,
        description="Operational status: healthy, degraded, or critical",
    )
    requests_per_minute: float = Field(
        ...,
        ge=0.0,
        description="Request throughput per minute for this service",
    )
    average_latency_ms: float = Field(
        ...,
        ge=0.0,
        description="Average request latency in milliseconds for this service",
    )
    error_rate: float = Field(
        0.0,
        ge=0.0,
        description="HTTP 5xx error percentage over the recent window",
    )


class ServicesListResponse(BaseModel):
    """Schema for GET /services response."""

    services: list[ServiceHealthItem]


class DashboardOverviewResponse(BaseModel):
    """Schema for GET /dashboard/overview."""

    system_health: int = Field(
        ...,
        ge=0,
        le=100,
        description="Overall system health score between 0 and 100",
    )
    active_incidents: int = Field(
        ...,
        ge=0,
        description="Number of active/unresolved incidents in PostgreSQL",
    )
    error_rate: float = Field(
        ...,
        ge=0.0,
        description="Current 5xx error rate percentage across services",
    )
    average_latency_ms: float = Field(
        ...,
        ge=0.0,
        description="Average request latency in milliseconds",
    )
    average_latency: float = Field(
        ...,
        ge=0.0,
        description="Alias for average_latency_ms",
    )
    healthy_services: int = Field(
        ...,
        ge=0,
        description="Count of services currently in healthy status",
    )
    total_services: int = Field(
        ...,
        ge=0,
        description="Total number of monitored microservices",
    )
    requests_per_minute: float = Field(
        ...,
        ge=0.0,
        description="Total request volume per minute across services",
    )
    request_rate: float = Field(
        ...,
        ge=0.0,
        description="Alias for requests_per_minute",
    )
    services: list[ServiceHealthItem] = Field(
        default_factory=list,
        description="List of service status items",
    )


class MonitoringMetricItem(BaseModel):
    """Schema for cluster/infrastructure metric card in GET /monitoring."""

    name: str
    display_value: str
    numeric_value: float | None = None
    unit: str
    sparkline: list[float] = Field(default_factory=list)
    is_available: bool = True


class PrometheusAlertRuleItem(BaseModel):
    """Schema for individual Prometheus alert rule in GET /monitoring."""

    name: str
    query: str
    severity: str
    status: str


class MonitoringResponse(BaseModel):
    """Schema for GET /monitoring response."""

    prometheus_up: bool
    cpu_utilization: MonitoringMetricItem
    memory_usage: MonitoringMetricItem
    network_throughput: MonitoringMetricItem
    alert_rules: list[PrometheusAlertRuleItem] = Field(default_factory=list)
    timestamp: str
