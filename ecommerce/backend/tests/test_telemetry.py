import json

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from shop_platform.logging_json import JsonFormatter
from shop_platform.telemetry import (
    RequestMetricsMiddleware,
    bind_commerce_metrics,
    record_db_query,
    record_payment_failure,
    record_payment_timeout,
)


def test_json_log_includes_trace_fields():
    formatter = JsonFormatter("ecommerce-shop-api")
    import logging

    record = logging.LogRecord("ecommerce.checkout", logging.INFO, __file__, 1, "order paid", (), None)
    payload = json.loads(formatter.format(record))
    assert payload["service"] == "ecommerce-shop-api"
    assert payload["message"] == "order paid"
    assert "trace_id" in payload
    assert "expected_root_cause" not in payload


def test_http_metrics_count_errors():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    middleware = RequestMetricsMiddleware(app=None, meter_provider=provider)
    middleware._record({"method": "GET"}, 500, 0.2)
    middleware._record({"method": "GET"}, 200, 0.1)
    data = reader.get_metrics_data()
    names = [metric.name for resource in data.resource_metrics for scope in resource.scope_metrics for metric in scope.metrics]
    assert "app_http_request_count" in names
    assert "app_http_error_count" in names
    assert "app_http_request_duration" in names


def test_commerce_metrics_bind():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    bind_commerce_metrics(provider.get_meter("test"))
    record_payment_failure()
    record_payment_timeout()
    record_db_query(0.01)
    data = reader.get_metrics_data()
    names = [metric.name for resource in data.resource_metrics for scope in resource.scope_metrics for metric in scope.metrics]
    assert "ecommerce_payment_failure_count" in names
    assert "ecommerce_payment_timeout_count" in names
    assert "ecommerce_db_query_duration" in names
