import logging
import os
import time
from importlib.util import find_spec

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


class RequestMetricsMiddleware:
    """Record stable, service-level HTTP metrics for Prometheus."""

    def __init__(self, app, meter_provider):
        self.app = app
        meter = meter_provider.get_meter("incident-investigation.http")
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

        start = time.perf_counter()
        status_code = 500

        async def send_with_status(message):
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        except Exception:
            self._record(scope, status_code, time.perf_counter() - start)
            raise
        else:
            self._record(scope, status_code, time.perf_counter() - start)

    def _record(self, scope, status_code, duration):
        attributes = {
            "http.method": scope.get("method", "UNKNOWN"),
            "http.status_code": status_code,
        }
        self.request_count.add(1, attributes)
        if status_code >= 500:
            self.error_count.add(1, attributes)
        self.request_duration.record(duration, attributes)


def configure_telemetry(app, engine, service_name):
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": os.getenv("ORDER_SERVICE_VERSION", "v1.3.1"),
            "deployment.environment": os.getenv(
                "DEPLOYMENT_ENVIRONMENT", "development"
            ),
        }
    )

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

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True))
    )
    set_logger_provider(logger_provider)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(
        LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    )

    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=tracer_provider, meter_provider=meter_provider
    )
    if find_spec("httpx") is not None:
        HTTPXClientInstrumentor().instrument(tracer_provider=tracer_provider)
    SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=tracer_provider)
    app.add_middleware(RequestMetricsMiddleware, meter_provider=meter_provider)
