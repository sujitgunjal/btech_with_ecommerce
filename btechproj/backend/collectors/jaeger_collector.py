"""Jaeger collector module bridge."""

try:
    from app.collectors.jaeger_collector import JaegerCollector
except ImportError:
    from backend.app.collectors.jaeger_collector import JaegerCollector

__all__ = ["JaegerCollector"]
