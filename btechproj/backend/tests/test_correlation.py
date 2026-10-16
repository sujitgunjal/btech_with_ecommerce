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
