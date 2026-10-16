"""Observability collectors for Prometheus, Loki, and Jaeger."""

try:
    from app.collectors.jaeger_collector import JaegerCollector
    from app.collectors.loki_collector import LokiCollector
    from app.collectors.prometheus_collector import PrometheusCollector
except ImportError:
    from backend.app.collectors.jaeger_collector import JaegerCollector
    from backend.app.collectors.loki_collector import LokiCollector
    from backend.app.collectors.prometheus_collector import PrometheusCollector

__all__ = [
    "LokiCollector",
    "PrometheusCollector",
    "JaegerCollector",
]
