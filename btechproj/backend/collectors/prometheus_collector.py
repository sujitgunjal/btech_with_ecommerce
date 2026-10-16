"""Prometheus collector module bridge."""

try:
    from app.collectors.prometheus_collector import PrometheusCollector
except ImportError:
    from backend.app.collectors.prometheus_collector import PrometheusCollector

__all__ = ["PrometheusCollector"]
