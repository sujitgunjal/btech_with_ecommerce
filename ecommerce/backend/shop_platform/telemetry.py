"""OpenTelemetry setup aligned with the existing collector pipeline.

Metrics use the same instrument names as the DevOps project so Prometheus
queries for app_http_request_count_total, app_http_error_count_total, and
app_http_request_duration_seconds keep working after the collector export.
"""

from __future__ import annotations

import logging
import time

from opentelemetry import metrics, trace
from opentelemetry.sdk.resources import Resource

logger = logging.getLogger("ecommerce.telemetry")

_commerce = {
    "payment_failures": None,
    "payment_timeouts": None,
    "checkout_errors": None,
    "inventory_conflicts": None,
    "order_duration": None,
    "db_query_duration": None,
}


def record_payment_failure() -> None:
    if _commerce["payment_failures"] is not None:
        _commerce["payment_failures"].add(1)


def record_payment_timeout() -> None:
    if _commerce["payment_timeouts"] is not None:
        _commerce["payment_timeouts"].add(1)


def record_db_query(seconds: float) -> None:
    if _commerce["db_query_duration"] is not None and seconds >= 0:
        _commerce["db_query_duration"].record(seconds)


def record_checkout_error() -> None:
    if _commerce["checkout_errors"] is not None:
        _commerce["checkout_errors"].add(1)


def record_inventory_conflict() -> None:
    if _commerce["inventory_conflicts"] is not None:
        _commerce["inventory_conflicts"].add(1)


def record_order_duration(seconds: float, outcome: str) -> None:
    if _commerce["order_duration"] is not None:
        _commerce["order_duration"].record(seconds, {"outcome": outcome})


def bind_commerce_metrics(meter) -> None:
    _commerce["payment_failures"] = meter.create_counter(
        "ecommerce_payment_failure_count",
        unit="{failure}",
        description="Payment charges that failed before approval",
    )
    _commerce["payment_timeouts"] = meter.create_counter(
        "ecommerce_payment_timeout_count",
        unit="{timeout}",
        description="Checkout calls that exceeded the payment gateway timeout",
    )
    _commerce["db_query_duration"] = meter.create_histogram(
        "ecommerce_db_query_duration",
        unit="s",
        description="Database statement duration in seconds",
    )
    _commerce["checkout_errors"] = meter.create_counter(
        "ecommerce_checkout_error_count",
        unit="{error}",
        description="Checkout attempts that did not result in a paid order",
    )
    _commerce["inventory_conflicts"] = meter.create_counter(
        "ecommerce_inventory_conflict_count",
        unit="{conflict}",
        description="Checkout reservations rejected because of inventory conflicts",
    )
    _commerce["order_duration"] = meter.create_histogram(
        "ecommerce_order_processing_duration",
        unit="s",
        description="Time spent processing a checkout attempt",
    )


class RequestMetricsMiddleware:
    """Record the HTTP instruments the existing Prometheus collector queries."""

    def __init__(self, app, meter_provider):
        self.app = app
        meter = meter_provider.get_meter("ecommerce.http")
        self.request_count = meter.create_counter(
            "app_http_request_count",
            unit="{request}",
            description="Number of HTTP requests received by the service",
        )
        self.error_count = meter.create_counter(
            "app_http_error_count",
            unit="{error}",
            description="Number of HTTP requests returning a 5xx status",
        )
        self.request_duration = meter.create_histogram(
            "app_http_request_duration",
            unit="s",
            description="HTTP request duration in seconds",
        )

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path.startswith(("/health", "/ops", "/docs", "/redoc", "/openapi.json")):
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500

        async def send_with_status(message):
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = message.get("status", 500)
            await send(message)

        internal = path.startswith("/internal")
        try:
            await self.app(scope, receive, send_with_status)
        except Exception:
            if not internal:
                self._record(scope, status_code, time.perf_counter() - start)
            self._log_request(scope, status_code, time.perf_counter() - start)
            raise
        else:
            if not internal:
                self._record(scope, status_code, time.perf_counter() - start)
            self._log_request(scope, status_code, time.perf_counter() - start)

    def _record(self, scope, status_code, duration):
        status = str(status_code)
        attributes = {
            "http.method": scope.get("method", "UNKNOWN"),
            "http.status_code": status_code,
            "status": status,
        }
        self.request_count.add(1, attributes)
        if status_code >= 500:
            self.error_count.add(1, attributes)
        self.request_duration.record(duration, attributes)

    def _log_request(self, scope, status_code, duration):
        logging.getLogger("ecommerce.http").log(
            logging.ERROR if status_code >= 500 else logging.INFO,
            "http request method=%s path=%s status=%s duration_ms=%.1f",
            scope.get("method", "UNKNOWN"),
            scope.get("path", ""),
            status_code,
            duration * 1000,
        )


def init_telemetry(app, engine, service_name: str, endpoint: str, environment: str):
    """Export OTLP only when an endpoint is configured. Requests still succeed without one."""
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": "1.0.0",
            "deployment.environment": environment,
        }
    )
    if not endpoint:
        logger.info("OTLP endpoint is empty; telemetry export is disabled")
        meter_provider = metrics.get_meter_provider()
        bind_commerce_metrics(meter_provider.get_meter("ecommerce.commerce"))
        return

    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=True),
        export_interval_millis=5000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)
    bind_commerce_metrics(meter_provider.get_meter("ecommerce.commerce"))

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True))
    )
    set_logger_provider(logger_provider)
    logging.getLogger().addHandler(
        LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    )
    LoggingInstrumentor().instrument(set_logging_format=False)

    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=tracer_provider, meter_provider=meter_provider
    )
    HTTPXClientInstrumentor().instrument(tracer_provider=tracer_provider)
    if engine is not None:
        SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=tracer_provider)
    app.add_middleware(RequestMetricsMiddleware, meter_provider=meter_provider)
