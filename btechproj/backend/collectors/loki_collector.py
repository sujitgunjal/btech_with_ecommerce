"""Loki collector module bridge."""

try:
    from app.collectors.loki_collector import LokiCollector
except ImportError:
    from backend.app.collectors.loki_collector import LokiCollector

__all__ = ["LokiCollector"]
