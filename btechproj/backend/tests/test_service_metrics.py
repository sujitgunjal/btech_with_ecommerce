from app.service_metrics import summarize_service_traffic


def test_successful_requests_have_latency_and_zero_errors():
    result = summarize_service_traffic(
        telemetry_present=True,
        request_count=4,
        error_count=0,
        duration_total=800,
        duration_unit="ms",
    )
    assert result["requests_per_minute"] == 0.3
    assert result["average_latency_ms"] == 200.0
    assert result["error_rate"] == 0.0


def test_failed_requests_use_the_error_count():
    result = summarize_service_traffic(
        telemetry_present=True,
        request_count=10,
        error_count=4,
        duration_total=2.5,
        duration_unit="s",
    )
    assert result["average_latency_ms"] == 250.0
    assert result["error_rate"] == 40.0


def test_mixed_traffic_keeps_a_real_zero_latency_distinct_from_missing_errors():
    result = summarize_service_traffic(
        telemetry_present=True,
        request_count=5,
        error_count=None,
        duration_total=0,
        duration_unit="ms",
    )
    assert result["average_latency_ms"] == 0.0
    assert result["error_rate"] == 0.0


def test_no_telemetry_is_unknown_rather_than_zero():
    result = summarize_service_traffic(
        telemetry_present=False,
        request_count=None,
        error_count=None,
        duration_total=None,
        duration_unit="ms",
    )
    assert result == {
        "requests_per_minute": None,
        "average_latency_ms": None,
        "error_rate": None,
    }


def test_series_with_no_requests_in_the_window_does_not_invent_zero_latency():
    result = summarize_service_traffic(
        telemetry_present=True,
        request_count=0,
        error_count=0,
        duration_total=0,
        duration_unit="ms",
    )
    assert result["requests_per_minute"] == 0.0
    assert result["average_latency_ms"] is None
    assert result["error_rate"] is None
