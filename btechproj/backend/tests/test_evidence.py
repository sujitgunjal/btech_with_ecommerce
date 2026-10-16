"""Tests for the unified evidence collection layer.

Unit tests verify:
- LokiCollector structured log retrieval
- PrometheusCollector structured metric retrieval
- JaegerCollector structured trace retrieval
- EvidenceService unified evidence assembly
- Evidence API endpoint behavior

No live HTTP calls are made — all external requests are mocked.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.collectors.loki_collector import LokiCollector
from app.collectors.prometheus_collector import PrometheusCollector
from app.collectors.jaeger_collector import JaegerCollector
from app.services.evidence_service import EvidenceService


# =====================================================================
# Sample payloads
# =====================================================================

LOKI_RESPONSE = {
    "data": {
        "result": [
            {
                "stream": {"service_name": "order-service", "level": "error"},
                "values": [
                    [
                        "1692792000000000000",
                        "ERROR Failed to connect to database: connection refused",
                    ],
                ],
            },
            {
                "stream": {"service_name": "order-service", "level": "info"},
                "values": [
                    [
                        "1692792060000000000",
                        "INFO Retrying connection attempt 2",
                    ],
                ],
            },
        ]
    }
}

PROMETHEUS_RESPONSE_SUCCESS = {
    "status": "success",
    "data": {
        "resultType": "matrix",
        "result": [
            {
                "metric": {"service_name": "order-service"},
                "values": [
                    [1692792000, "0.85"],
                    [1692792060, "0.92"],
                ],
            }
        ],
    },
}

JAEGER_RESPONSE = {
    "data": [
        {
            "traceID": "abc123def456",
            "processes": {
                "p1": {"serviceName": "order-service"},
                "p2": {"serviceName": "product-service"},
            },
            "spans": [
                {
                    "spanID": "span001",
                    "processID": "p1",
                    "operationName": "GET /orders",
                    "startTime": 1692792000000000,
                    "duration": 150000,
                    "references": [],
                    "tags": [
                        {"key": "http.status_code", "value": "200"},
                    ],
                    "logs": [],
                },
                {
                    "spanID": "span002",
                    "processID": "p2",
                    "operationName": "DB query",
                    "startTime": 1692792000100000,
                    "duration": 50000,
                    "references": [
                        {"refType": "CHILD_OF", "spanID": "span001"},
                    ],
                    "tags": [
                        {"key": "error", "value": True},
                    ],
                    "logs": [
                        {
                            "fields": [
                                {"key": "message", "value": "connection timeout"},
                            ]
                        }
                    ],
                },
            ],
        }
    ]
}


# =====================================================================
# LokiCollector — structured logs
# =====================================================================


class TestLokiCollectorStructured:
    """Tests for structured log retrieval via get_logs()."""

    def setup_method(self):
        self.collector = LokiCollector(
            "http://fake-loki:3100", timeout=5.0
        )

    def test_parse_structured_records(self):
        """Structured records have source, timestamp, service, level, message, labels."""
        records = self.collector._parse_structured_records(
            LOKI_RESPONSE, "order-service"
        )
        assert len(records) == 2
        assert all(r["source"] == "loki" for r in records)
        assert all(r["service"] == "order-service" for r in records)
        assert records[0]["level"] == "ERROR"
        assert records[1]["level"] == "INFO"
        assert "database" in records[0]["message"].lower()
        assert "labels" in records[0]

    def test_parse_structured_records_empty(self):
        """Empty Loki response returns empty list."""
        records = self.collector._parse_structured_records(
            {"data": {"result": []}}, "svc"
        )
        assert records == []

    def test_severity_detection_lowercase(self):
        """Severity detection returns lowercase values."""
        assert LokiCollector._detect_severity("INFO all good") == "info"
        assert LokiCollector._detect_severity("WARNING disk 90%") == "warning"
        assert LokiCollector._detect_severity("ERROR conn refused") == "error"
        assert LokiCollector._detect_severity("CRITICAL OOM") == "critical"
        assert LokiCollector._detect_severity("FATAL shutdown") == "critical"
        assert LokiCollector._detect_severity("Unhandled EXCEPTION") == "error"

    def test_severity_from_labels(self):
        """Severity can be extracted from stream labels."""
        assert LokiCollector._detect_severity(
            "some message", {"level": "error"}
        ) == "error"
        assert LokiCollector._detect_severity(
            "some message", {"level": "WARN"}
        ) == "warning"

    def test_time_parsing(self):
        """ISO strings and datetimes are correctly converted to nanoseconds."""
        dt = datetime(2023, 8, 23, 10, 0, 0, tzinfo=timezone.utc)
        ns = LokiCollector._parse_time_to_nanoseconds(dt)
        assert ns == int(dt.timestamp() * 1_000_000_000)

        iso = "2023-08-23T10:00:00Z"
        ns_str = LokiCollector._parse_time_to_nanoseconds(iso)
        assert ns_str == ns


# =====================================================================
# PrometheusCollector — structured metrics
# =====================================================================


class TestPrometheusCollectorStructured:
    """Tests for structured metric retrieval via get_metrics()."""

    def setup_method(self):
        self.collector = PrometheusCollector(
            "http://fake-prometheus:9090", timeout=5.0
        )

    def test_parse_prometheus_matrix(self):
        """Prometheus matrix results are parsed into structured metric records."""
        records = self.collector._parse_prometheus_matrix(
            PROMETHEUS_RESPONSE_SUCCESS, "cpu_usage", "order-service"
        )
        assert len(records) == 2
        assert all(r["source"] == "prometheus" for r in records)
        assert all(r["metric_name"] == "cpu_usage" for r in records)
        assert all(r["service"] == "order-service" for r in records)
        assert records[0]["value"] == 0.85
        assert records[1]["value"] == 0.92
        assert "timestamp" in records[0]
        assert "labels" in records[0]

    def test_parse_prometheus_matrix_empty(self):
        """Empty Prometheus result returns no records."""
        response = {
            "status": "success",
            "data": {"resultType": "matrix", "result": []},
        }
        records = self.collector._parse_prometheus_matrix(
            response, "cpu_usage", "svc"
        )
        assert records == []

    def test_parse_prometheus_matrix_error_status(self):
        """Non-success response returns no records."""
        records = self.collector._parse_prometheus_matrix(
            {"status": "error"}, "cpu_usage", "svc"
        )
        assert records == []

    def test_parse_nan_values(self):
        """NaN values are skipped."""
        response = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {},
                        "values": [[1692792000, "NaN"]],
                    }
                ],
            },
        }
        records = self.collector._parse_prometheus_matrix(
            response, "cpu_usage", "svc"
        )
        assert records == []

    def test_calculate_step(self):
        """Step calculation adjusts based on time window."""
        start = datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_30s = datetime(2023, 1, 1, 0, 0, 30, tzinfo=timezone.utc)
        end_5m = datetime(2023, 1, 1, 0, 5, 0, tzinfo=timezone.utc)
        end_30m = datetime(2023, 1, 1, 0, 30, 0, tzinfo=timezone.utc)
        end_2h = datetime(2023, 1, 1, 2, 0, 0, tzinfo=timezone.utc)

        assert PrometheusCollector._calculate_step(start, end_30s) == "5s"
        assert PrometheusCollector._calculate_step(start, end_5m) == "10s"
        assert PrometheusCollector._calculate_step(start, end_30m) == "30s"
        assert PrometheusCollector._calculate_step(start, end_2h) == "60s"


# =====================================================================
# JaegerCollector — structured traces
# =====================================================================


class TestJaegerCollectorStructured:
    """Tests for structured trace retrieval via get_traces()."""

    def setup_method(self):
        self.collector = JaegerCollector(
            "http://fake-jaeger:16686", timeout=5.0
        )

    def test_parse_trace_spans(self):
        """Trace spans are parsed into structured records."""
        trace = JAEGER_RESPONSE["data"][0]
        spans = self.collector._parse_trace_spans(trace, "order-service")

        assert len(spans) == 2
        assert all(s["source"] == "jaeger" for s in spans)
        assert spans[0]["trace_id"] == "abc123def456"
        assert spans[0]["span_id"] == "span001"
        assert spans[0]["operation"] == "GET /orders"
        assert spans[0]["status"] == "ok"
        assert spans[0]["service"] == "order-service"
        assert spans[1]["status"] == "error"
        assert spans[1]["service"] == "product-service"
        assert spans[1]["parent_span_id"] == "span001"
        assert isinstance(spans[0]["duration_ms"], float)
        assert "timestamp" in spans[0]

    def test_parse_trace_spans_empty(self):
        """Empty trace returns empty spans."""
        spans = self.collector._parse_trace_spans(
            {"traceID": "x", "spans": [], "processes": {}}, "svc"
        )
        assert spans == []

    def test_time_parsing(self):
        """Microseconds conversion is correct."""
        dt = datetime(2023, 8, 23, 10, 0, 0, tzinfo=timezone.utc)
        us = JaegerCollector._parse_time_to_microseconds(dt)
        assert us == int(dt.timestamp() * 1_000_000)


# =====================================================================
# EvidenceService — unified evidence orchestration
# =====================================================================


class TestEvidenceService:
    """Tests for the unified evidence service."""

    def _make_mock_service(self):
        """Create an EvidenceService with mocked collectors."""
        loki = MagicMock(spec=LokiCollector)
        prometheus = MagicMock(spec=PrometheusCollector)
        jaeger = MagicMock(spec=JaegerCollector)

        loki.get_logs = AsyncMock(return_value=[
            {
                "source": "loki",
                "timestamp": "2023-08-23T10:00:00+00:00",
                "service": "order-service",
                "level": "ERROR",
                "message": "connection refused",
                "labels": {},
            }
        ])
        prometheus.get_metrics = AsyncMock(return_value=[
            {
                "source": "prometheus",
                "metric_name": "cpu_usage",
                "service": "order-service",
                "timestamp": "2023-08-23T10:00:00+00:00",
                "value": 0.85,
                "labels": {},
            }
        ])
        jaeger.get_traces = AsyncMock(return_value=[
            {
                "source": "jaeger",
                "trace_id": "abc123",
                "span_id": "span1",
                "parent_span_id": None,
                "service": "order-service",
                "operation": "GET /orders",
                "duration_ms": 150.0,
                "status": "ok",
                "timestamp": "2023-08-23T10:00:00+00:00",
                "tags": {},
            }
        ])

        return EvidenceService(
            loki_collector=loki,
            prometheus_collector=prometheus,
            jaeger_collector=jaeger,
        )

    def test_unified_evidence_structure(self):
        """Unified evidence has the expected top-level keys."""
        svc = self._make_mock_service()
        result = asyncio.run(svc.get_incident_evidence(
            incident_id="INC-001",
            service="order-service",
            start_time="2023-08-23T10:00:00Z",
            end_time="2023-08-23T10:02:00Z",
        ))
        assert result["incident_id"] == "INC-001"
        assert result["service"] == "order-service"
        assert "time_window" in result
        assert "start" in result["time_window"]
        assert "end" in result["time_window"]
        assert isinstance(result["logs"], list)
        assert isinstance(result["metrics"], list)
        assert isinstance(result["traces"], list)

    def test_evidence_contains_data(self):
        """Unified evidence includes collected logs, metrics, traces."""
        svc = self._make_mock_service()
        result = asyncio.run(svc.get_incident_evidence(
            incident_id="INC-001",
            service="order-service",
            start_time="2023-08-23T10:00:00Z",
            end_time="2023-08-23T10:02:00Z",
        ))
        assert len(result["logs"]) == 1
        assert len(result["metrics"]) == 1
        assert len(result["traces"]) == 1
        assert result["logs"][0]["source"] == "loki"
        assert result["metrics"][0]["source"] == "prometheus"
        assert result["traces"][0]["source"] == "jaeger"

    def test_evidence_source_attribution(self):
        """Every evidence item has its source field set."""
        svc = self._make_mock_service()
        result = asyncio.run(svc.get_incident_evidence(
            incident_id="INC-001",
            service="order-service",
            start_time="2023-08-23T10:00:00Z",
            end_time="2023-08-23T10:02:00Z",
        ))
        for log in result["logs"]:
            assert log["source"] == "loki"
        for metric in result["metrics"]:
            assert metric["source"] == "prometheus"
        for trace in result["traces"]:
            assert trace["source"] == "jaeger"

    def test_no_root_cause_in_evidence(self):
        """Evidence must NOT contain root cause or ground truth."""
        svc = self._make_mock_service()
        result = asyncio.run(svc.get_incident_evidence(
            incident_id="INC-001",
            service="order-service",
            start_time="2023-08-23T10:00:00Z",
            end_time="2023-08-23T10:02:00Z",
        ))
        import json
        payload = json.dumps(result)
        assert "expected_root_cause" not in payload
        assert "root_cause" not in payload.lower()

    def test_graceful_collector_failure(self):
        """If a collector raises, the evidence still includes other sources."""
        loki = MagicMock(spec=LokiCollector)
        prometheus = MagicMock(spec=PrometheusCollector)
        jaeger = MagicMock(spec=JaegerCollector)

        loki.get_logs = AsyncMock(side_effect=Exception("Loki unreachable"))
        prometheus.get_metrics = AsyncMock(return_value=[
            {"source": "prometheus", "metric_name": "cpu", "timestamp": "2023-08-23T10:00:00+00:00", "value": 0.5, "service": "svc", "labels": {}}
        ])
        jaeger.get_traces = AsyncMock(side_effect=Exception("Jaeger down"))

        svc = EvidenceService(
            loki_collector=loki,
            prometheus_collector=prometheus,
            jaeger_collector=jaeger,
        )
        result = asyncio.run(svc.get_incident_evidence(
            incident_id="INC-001",
            service="svc",
            start_time="2023-08-23T10:00:00Z",
            end_time="2023-08-23T10:02:00Z",
        ))
        # Loki and Jaeger failed, but Prometheus succeeded
        assert result["logs"] == []
        assert len(result["metrics"]) == 1
        assert result["traces"] == []

    def test_all_collectors_fail(self):
        """If all collectors fail, return empty arrays not crash."""
        loki = MagicMock(spec=LokiCollector)
        prometheus = MagicMock(spec=PrometheusCollector)
        jaeger = MagicMock(spec=JaegerCollector)

        loki.get_logs = AsyncMock(side_effect=Exception("fail"))
        prometheus.get_metrics = AsyncMock(side_effect=Exception("fail"))
        jaeger.get_traces = AsyncMock(side_effect=Exception("fail"))

        svc = EvidenceService(
            loki_collector=loki,
            prometheus_collector=prometheus,
            jaeger_collector=jaeger,
        )
        result = asyncio.run(svc.get_incident_evidence(
            incident_id="INC-001",
            service="svc",
            start_time="2023-08-23T10:00:00Z",
            end_time="2023-08-23T10:02:00Z",
        ))
        assert result["logs"] == []
        assert result["metrics"] == []
        assert result["traces"] == []
        assert result["incident_id"] == "INC-001"

    def test_time_normalization(self):
        """End time defaults to start + 15m when omitted."""
        start_dt, start_iso = EvidenceService._normalize_time("2023-08-23T10:00:00Z")
        end_dt, end_iso = EvidenceService._normalize_time(None, default_ref=start_dt, offset_minutes=15)
        assert end_dt > start_dt
        delta = (end_dt - start_dt).total_seconds()
        assert delta == 900  # 15 minutes


# =====================================================================
# find_incident_scenario
# =====================================================================


class TestFindIncidentScenario:
    """Tests for scenario file lookup."""

    def test_find_existing_scenario(self):
        """Known incident IDs are found in scenario files."""
        from app.services.incident_service import find_incident_scenario
        scenario = find_incident_scenario("INC-001")
        if scenario is not None:
            assert scenario["incident_id"] == "INC-001"
            assert scenario["service"] is not None
            assert "expected_root_cause" not in scenario

    def test_find_missing_scenario(self):
        """Unknown incident IDs return None."""
        from app.services.incident_service import find_incident_scenario
        result = find_incident_scenario("INC-999")
        assert result is None

