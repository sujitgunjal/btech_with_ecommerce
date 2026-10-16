"""Tests for telemetry collectors.

Unit tests verify the normalization/parsing logic by calling
internal helper methods directly with sample payloads.
No live HTTP calls are made.
"""

from datetime import datetime, timezone

from app.collectors.jaeger import JaegerCollector
from app.collectors.loki import LokiCollector
from app.collectors.prometheus import PrometheusCollector


# =================================================================
# Prometheus
# =================================================================


class TestPrometheusCollector:
    """Tests for PrometheusCollector parsing and severity logic."""

    def setup_method(self):
        self.collector = PrometheusCollector(
            "http://fake-prometheus:9090", timeout=5.0
        )

    def test_to_events_success(self):
        """Valid Prometheus response is parsed into NormalizedEvents."""
        response = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"container": "order-service"},
                        "values": [
                            [1692792000, "0.85"],
                            [1692792060, "0.92"],
                        ],
                    }
                ],
            },
        }

        events = self.collector._to_events(
            response, "order-service", "cpu_usage"
        )

        assert len(events) == 2
        assert all(e.source == "prometheus" for e in events)
        assert all(e.event_type == "cpu_usage" for e in events)
        assert events[0].severity == "warning"  # 0.85 > 0.7
        assert events[1].severity == "error"  # 0.92 > 0.9

    def test_to_events_empty_result(self):
        """Empty Prometheus result returns no events."""
        response = {
            "status": "success",
            "data": {"resultType": "matrix", "result": []},
        }
        events = self.collector._to_events(
            response, "order-service", "cpu_usage"
        )
        assert events == []

    def test_to_events_failed_status(self):
        """Non-success status returns no events."""
        response = {"status": "error", "error": "bad query"}
        events = self.collector._to_events(
            response, "order-service", "cpu_usage"
        )
        assert events == []

    def test_to_events_malformed_value(self):
        """Non-numeric values are skipped gracefully."""
        response = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {},
                        "values": [[1692792000, "NaN_bad"]],
                    }
                ],
            },
        }
        events = self.collector._to_events(
            response, "svc", "cpu_usage"
        )
        assert events == []

    def test_severity_thresholds(self):
        """Severity is determined by metric-specific thresholds."""
        assert (
            PrometheusCollector._determine_severity("cpu_usage", 0.5)
            == "info"
        )
        assert (
            PrometheusCollector._determine_severity("cpu_usage", 0.75)
            == "warning"
        )
        assert (
            PrometheusCollector._determine_severity("cpu_usage", 0.91)
            == "error"
        )
        assert (
            PrometheusCollector._determine_severity("cpu_usage", 0.96)
            == "critical"
        )
        # Unknown metric always returns info
        assert (
            PrometheusCollector._determine_severity("unknown", 999)
            == "info"
        )

    def test_instant_query_format(self):
        """Instant query format (single 'value') is handled."""
        response = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {
                        "metric": {"container": "svc"},
                        "value": [1692792000, "0.5"],
                    }
                ],
            },
        }
        events = self.collector._to_events(
            response, "svc", "request_rate"
        )
        assert len(events) == 1


# =================================================================
# Loki
# =================================================================


class TestLokiCollector:
    """Tests for LokiCollector parsing and severity detection."""

    def setup_method(self):
        self.collector = LokiCollector(
            "http://fake-loki:3100", timeout=5.0
        )

    def test_parse_response_success(self):
        """Valid Loki response is parsed into NormalizedEvents."""
        data = {
            "data": {
                "result": [
                    {
                        "stream": {"container": "order-service"},
                        "values": [
                            [
                                "1692792000000000000",
                                "INFO Starting order processing",
                            ],
                            [
                                "1692792060000000000",
                                "ERROR Failed to connect to database",
                            ],
                        ],
                    }
                ]
            }
        }

        events = self.collector._parse_response(data, "order-service")

        assert len(events) == 2
        assert all(e.source == "loki" for e in events)
        assert all(e.event_type == "log_entry" for e in events)
        assert events[0].severity == "info"
        assert events[1].severity == "error"

    def test_parse_response_empty(self):
        """Empty Loki result returns no events."""
        data = {"data": {"result": []}}
        events = self.collector._parse_response(data, "svc")
        assert events == []

    def test_severity_detection(self):
        """Log severity is detected from content keywords."""
        assert LokiCollector._detect_severity("INFO all good") == "info"
        assert (
            LokiCollector._detect_severity("WARNING disk 90%")
            == "warning"
        )
        assert (
            LokiCollector._detect_severity("ERROR connection refused")
            == "error"
        )
        assert (
            LokiCollector._detect_severity("CRITICAL out of memory")
            == "critical"
        )
        assert (
            LokiCollector._detect_severity("FATAL shutdown")
            == "critical"
        )
        assert (
            LokiCollector._detect_severity(
                "Unhandled EXCEPTION in worker"
            )
            == "error"
        )


# =================================================================
# Jaeger
# =================================================================


class TestJaegerCollector:
    """Tests for JaegerCollector parsing and error detection."""

    def setup_method(self):
        self.collector = JaegerCollector(
            "http://fake-jaeger:16686", timeout=5.0
        )

    def test_parse_response_success(self):
        """Valid Jaeger response is parsed into NormalizedEvents."""
        data = {
            "data": [
                {
                    "traceID": "abc123",
                    "spans": [
                        {
                            "spanID": "span1",
                            "operationName": "GET /orders",
                            "startTime": 1692792000000000,
                            "duration": 150000,
                            "tags": [
                                {
                                    "key": "http.status_code",
                                    "value": "200",
                                }
                            ],
                            "logs": [],
                        },
                        {
                            "spanID": "span2",
                            "operationName": "DB query",
                            "startTime": 1692792000100000,
                            "duration": 50000,
                            "tags": [
                                {
                                    "key": "error",
                                    "value": True,
                                }
                            ],
                            "logs": [
                                {
                                    "fields": [
                                        {
                                            "key": "message",
                                            "value": "timeout",
                                        }
                                    ]
                                }
                            ],
                        },
                    ],
                }
            ]
        }

        events = self.collector._parse_response(data, "order-service")

        assert len(events) == 2
        assert all(e.source == "jaeger" for e in events)
        assert events[0].severity == "info"
        assert events[1].severity == "error"
        assert "timeout" in events[1].content

    def test_parse_response_empty(self):
        """Empty Jaeger result returns no events."""
        data = {"data": []}
        events = self.collector._parse_response(data, "svc")
        assert events == []

    def test_span_error_detection(self):
        """Error detection works for various tag formats."""
        # error=true tag
        span_error = {"tags": [{"key": "error", "value": True}]}
        assert JaegerCollector._span_has_error(span_error) is True

        # otel status code
        span_otel = {
            "tags": [
                {"key": "otel.status_code", "value": "ERROR"}
            ]
        }
        assert JaegerCollector._span_has_error(span_otel) is True

        # HTTP 500
        span_http = {
            "tags": [{"key": "http.status_code", "value": "503"}]
        }
        assert JaegerCollector._span_has_error(span_http) is True

        # HTTP 200 — not an error
        span_ok = {
            "tags": [{"key": "http.status_code", "value": "200"}]
        }
        assert JaegerCollector._span_has_error(span_ok) is False

        # No tags
        assert JaegerCollector._span_has_error({"tags": []}) is False

    def test_extract_error_message(self):
        """Error messages are extracted from span logs."""
        span = {
            "logs": [
                {
                    "fields": [
                        {"key": "message", "value": "connection reset"}
                    ]
                }
            ]
        }
        assert (
            JaegerCollector._extract_error_message(span)
            == "connection reset"
        )

        # No logs
        assert (
            JaegerCollector._extract_error_message({"logs": []}) is None
        )
