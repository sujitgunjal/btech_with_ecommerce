from datetime import datetime, timezone

from app.schemas.evidence import NormalizedEvent
from app.services.correlation import correlation_events, correlation_notes


def test_shared_trace_is_correlation_not_causation():
    records = [
        {
            "service": "ecommerce-shop-api",
            "trace_id": "abc123",
            "content": "checkout",
            "status": "error",
        },
        {
            "service": "ecommerce-payment-gateway",
            "trace_id": "abc123",
            "content": "charge",
            "status": "error",
        },
    ]
    notes = correlation_notes(records)
    relations = {note["relation"] for note in notes}
    assert "shared_trace" in relations
    assert "temporal_cooccurrence" in relations
    assert all(note["causation"] == "not_established" for note in notes)
    assert "caused" not in " ".join(note["content"] for note in notes)


def test_single_service_trace_produces_no_correlation():
    event = NormalizedEvent(
        timestamp=datetime.now(timezone.utc),
        source="jaeger",
        service="ecommerce-shop-api",
        event_type="trace",
        severity="info",
        content="Span GET /products duration=12.0ms trace=onlyone",
        metadata={"trace_id": "onlyone"},
    )
    assert correlation_events([event]) == []


def test_timestamp_match_links_a_failure_log_to_a_nearby_metric():
    notes = correlation_notes(
        [
            {
                "source": "loki",
                "service": "ecommerce-shop-api",
                "event_type": "log_entry",
                "severity": "error",
                "timestamp": "2026-10-16T13:00:00Z",
                "content": "http request failed method=POST path=/checkout status=504",
            },
            {
                "source": "prometheus",
                "service": "ecommerce-shop-api",
                "event_type": "latency",
                "severity": "info",
                "timestamp": "2026-10-16T13:00:10Z",
                "content": "request latency increased",
            },
        ],
        tolerance_seconds=30,
    )
    match = next(note for note in notes if note["relation"] == "timestamp")
    assert match["matching_method"] == "time_window"
    assert match["time_difference_seconds"] == 10
    assert match["causation"] == "not_established"
    assert "loki:0" in match["evidence_refs"]
    assert "prometheus:1" in match["evidence_refs"]


def test_cross_service_dependency_can_match_by_time():
    notes = correlation_notes(
        [
            {
                "source": "loki",
                "service": "ecommerce-shop-api",
                "event_type": "log_entry",
                "severity": "error",
                "timestamp": "2026-10-16T13:00:00Z",
                "content": "payment gateway timed out",
            },
            {
                "source": "prometheus",
                "service": "ecommerce-payment-gateway",
                "event_type": "error_rate",
                "severity": "warning",
                "timestamp": "2026-10-16T13:00:05Z",
                "content": "gateway error rate rose",
            },
        ],
        tolerance_seconds=30,
    )
    assert any(note["relation"] == "timestamp" and set(note["services"]) == {
        "ecommerce-payment-gateway",
        "ecommerce-shop-api",
    } for note in notes)


def test_trace_id_connects_a_log_and_a_span():
    notes = correlation_notes(
        [
            {
                "source": "loki",
                "service": "ecommerce-shop-api",
                "event_type": "log_entry",
                "severity": "error",
                "timestamp": "2026-10-16T13:00:00Z",
                "content": json_log("abc123", "POST /checkout failed"),
            },
            {
                "source": "jaeger",
                "service": "ecommerce-shop-api",
                "event_type": "trace",
                "severity": "error",
                "timestamp": "2026-10-16T13:00:01Z",
                "trace_id": "abc123",
                "operation": "POST /checkout",
                "content": "Span POST /checkout duration=2100ms trace=abc123 status=error",
            },
        ]
    )
    assert any(note["relation"] == "trace_request" and note["matching_method"] == "trace_id" for note in notes)


def test_endpoint_links_a_log_and_span_without_a_shared_trace():
    notes = correlation_notes(
        [
            {
                "source": "loki",
                "service": "order-service",
                "event_type": "log_entry",
                "severity": "error",
                "timestamp": "2026-10-16T13:00:00Z",
                "content": "http request failed method=POST path=/orders status=500",
            },
            {
                "source": "jaeger",
                "service": "order-service",
                "event_type": "trace",
                "severity": "error",
                "timestamp": "2026-10-16T13:00:02Z",
                "trace_id": "trace-span-only",
                "operation": "POST /orders",
                "content": "Span POST /orders duration=800ms status=error",
            },
        ],
        tolerance_seconds=30,
    )
    match = next(note for note in notes if note["relation"] == "endpoint")
    assert match["matching_method"] == "endpoint"
    assert "/orders" in match["content"]
    assert match["time_difference_seconds"] == 2


def test_duplicate_pairs_are_not_emitted_twice():
    records = [
        {
            "source": "loki",
            "service": "ecommerce-shop-api",
            "event_type": "log_entry",
            "severity": "error",
            "timestamp": "2026-10-16T13:00:00Z",
            "trace_id": "same",
            "content": "POST /checkout failed",
        },
        {
            "source": "jaeger",
            "service": "ecommerce-payment-gateway",
            "event_type": "trace",
            "severity": "error",
            "timestamp": "2026-10-16T13:00:01Z",
            "trace_id": "same",
            "operation": "POST /charges",
            "content": "Span POST /charges status=error",
        },
    ]
    notes = correlation_notes(records)
    pair_keys = [
        (note["matching_method"], tuple(sorted(note["evidence_refs"])))
        for note in notes
        if len(note["evidence_refs"]) == 2
    ]
    assert len(pair_keys) == len(set(pair_keys))


def test_missing_timestamp_trace_and_endpoint_are_skipped():
    notes = correlation_notes(
        [
            {
                "source": "loki",
                "service": "ecommerce-shop-api",
                "event_type": "log_entry",
                "severity": "error",
                "content": "request failed",
            },
            {
                "source": "prometheus",
                "service": "ecommerce-shop-api",
                "event_type": "latency",
                "severity": "info",
                "content": "latency sample",
            },
        ]
    )
    assert notes == []


def test_unrelated_service_events_are_not_correlated():
    notes = correlation_notes(
        [
            {
                "source": "loki",
                "service": "user-service",
                "event_type": "log_entry",
                "severity": "error",
                "timestamp": "2026-10-16T13:00:00Z",
                "content": "login failed path=/login",
            },
            {
                "source": "jaeger",
                "service": "ecommerce-payment-gateway",
                "event_type": "trace",
                "severity": "error",
                "timestamp": "2026-10-16T13:00:01Z",
                "operation": "POST /charges",
                "content": "Span POST /charges status=error",
            },
        ],
        tolerance_seconds=30,
    )
    assert notes == []


def json_log(trace_id: str, message: str) -> str:
    import json
    return json.dumps({"trace_id": trace_id, "message": message})
