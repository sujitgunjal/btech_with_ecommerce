import re

from app.incident_chat import (
    asks_for_procedure,
    build_chat_messages,
    causal_answer,
    evidence_brief,
    fallback_answer,
    hypothesis_answer,
    metric_answer,
    parse_model_answer,
    procedure_answer,
    rows_from_stored,
    trace_answer,
    classify_question,
)


def test_insufficient_evidence_does_not_invent_telemetry():
    result = fallback_answer("Why did this fail?", None, "")
    assert result["certainty"] == "insufficient"
    assert result["evidence_refs"] == []
    assert "ms" not in result["answer"]
    assert "5xx" not in result["answer"].lower()


def test_alternative_causes_are_marked_as_hypotheses():
    result = fallback_answer(
        "What other causes are possible?",
        {"alternative_explanations": ["A slow dependency could explain the timeout."]},
        "log line",
    )
    assert result["certainty"] == "hypothesis"
    assert result["answer"].lower().startswith("hypothesis")


def test_invalid_evidence_references_are_dropped():
    result = parse_model_answer(
        '{"answer":"The checkout log shows a timeout.","certainty":"verified",'
        '"evidence_refs":[{"source":"logs","index":0,"label":"checkout log"},'
        '{"source":"logs","index":9,"label":"missing"},'
        '{"source":"traces","index":0,"label":"no traces"}]}',
        {"logs": [{"message": "timeout"}], "metrics": [], "traces": [], "correlations": []},
    )
    assert result["evidence_refs"] == [{"source": "logs", "index": 0, "label": "checkout log"}]


def test_experiment_names_are_removed_from_the_answer():
    result = parse_model_answer(
        '{"answer":"An memory_pressure experiment caused this.","certainty":"verified","evidence_refs":[]}',
        {"logs": [], "metrics": [], "traces": [], "correlations": []},
    )
    assert "memory_pressure" not in result["answer"]
    assert "experiment" not in result["answer"].lower()
    assert "observed condition" not in result["answer"]


def test_fault_paths_are_rewritten_once():
    result = parse_model_answer(
        '{"answer":"A POST /internal/faults/apply experiment preceded the rise.","certainty":"hypothesis","evidence_refs":[]}',
        {"logs": [{"message": "rise"}]},
    )
    assert "internal/faults" in result["answer"]
    assert "experiment" not in result["answer"].lower()


def test_verified_claims_need_a_real_evidence_reference():
    result = parse_model_answer(
        '{"answer":"Latency is 3000 ms.","certainty":"verified","evidence_refs":[{"source":"metrics","index":4,"label":"missing"}]}',
        {"logs": [], "metrics": [{"metric_name": "latency"}], "traces": [], "correlations": []},
    )
    assert result["certainty"] == "hypothesis"
    assert result["evidence_refs"] == []


def test_latency_steps_quote_collected_spans_and_do_not_invent_another():
    result = procedure_answer(
        "How do I separate endpoint duration from the payment dependency?",
        {"service": "ecommerce-shop-api", "start_time": "2026-10-17T05:55:08Z", "end_time": "2026-10-17T05:55:53Z"},
        {"recommended_actions": ["Compare checkout latency with the payment call."]},
        {
            "logs": [],
            "metrics": [],
            "traces": [
                {"trace_id": "abc", "span_id": "p", "operation": "POST /checkout", "service": "ecommerce-shop-api", "duration_ms": 2100},
                {"trace_id": "abc", "span_id": "c", "parent_span_id": "p", "operation": "POST /charges", "service": "ecommerce-payment-gateway", "duration_ms": 2000},
            ],
            "correlations": [],
        },
    )
    assert result["certainty"] == "procedure"
    assert "POST /checkout" in result["answer"]
    assert "2100" in result["answer"]
    assert "2000" in result["answer"]
    assert "leaves 100 ms" in result["answer"]
    assert "Open Jaeger" not in result["answer"]
    assert "more child spans" not in result["answer"]
    assert "9999" not in result["answer"]
    assert "No trace spans were stored" not in result["answer"]
    assert any(ref["source"] == "traces" for ref in result["evidence_refs"])


def test_missing_telemetry_still_gives_collection_steps_without_fake_numbers():
    result = procedure_answer(
        "How should I perform the recommended latency check?",
        {"service": "ecommerce-payment-gateway", "start_time": "2026-10-17T05:55:08Z"},
        None,
        {"logs": [], "metrics": [], "traces": [], "correlations": []},
    )
    assert "localhost:16686" in result["answer"]
    assert "localhost:9090" in result["answer"]
    assert "No spans were stored" in result["answer"]
    assert "No Prometheus samples were stored" in result["answer"]
    assert re.search(r"\d+\s*ms", result["answer"]) is None
    assert result["evidence_refs"] == []
    assert "lacks instructions" not in result["answer"].lower()


def test_prompt_says_history_is_not_proof_and_includes_the_report():
    assert asks_for_procedure("How do I separate endpoint duration?")
    assert not asks_for_procedure("Which evidence supports this?")
    messages = build_chat_messages(
        question="Which evidence supports this?",
        history=[{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}],
        incident={"service": "ecommerce-shop-api", "title": "checkout"},
        report={"root_cause": "Latency rose. Not established: the caller."},
        evidence_text=evidence_brief({"logs": [{"message": "status=504"}]}),
    )
    system = messages[0]["content"]
    assert "not proof" in system
    assert "insufficient" in system
    assert "Not established" in messages[-1]["content"]
    assert "[logs #0]" in messages[-1]["content"]


INC0069_EVIDENCE = {
    "logs": [
        {
            "timestamp": "2026-10-17T07:34:01.700785+00:00",
            "service": "ecommerce-shop-api",
            "message": 'HTTP Request: POST http://ecommerce-payment-gateway:8000/internal/faults/apply "HTTP/1.1 200 OK"',
        }
    ],
    "metrics": [
        {
            "timestamp": "2026-10-17T07:34:01.627+00:00",
            "service": "ecommerce-payment-gateway",
            "metric_name": "cpu_usage",
            "value": 0.04682079310532914,
            "labels": {},
        },
        {
            "timestamp": "2026-10-17T07:34:31.627+00:00",
            "service": "ecommerce-payment-gateway",
            "metric_name": "cpu_usage",
            "value": 0.5333326945106098,
            "labels": {},
        },
    ],
    "traces": [
        {
            "timestamp": "2026-10-17T07:34:15.122459+00:00",
            "service": "ecommerce-payment-gateway",
            "operation": "GET /health",
            "duration_ms": 61.028,
            "trace_id": "327efbd6b0fa595bdac1c58f8b76220e",
            "span_id": "5a986d5d935fc237",
        },
        {
            "timestamp": "2026-10-17T07:34:10+00:00",
            "service": "ecommerce-payment-gateway",
            "operation": "GET /internal/faults",
            "duration_ms": 20.246,
            "trace_id": "stored-faults-trace",
            "span_id": "span-faults",
        },
        {
            "timestamp": "2026-10-17T07:34:10+00:00",
            "service": "ecommerce-shop-api",
            "operation": "POST /checkout",
            "duration_ms": 9999,
            "trace_id": "shop-trace",
            "span_id": "shop-span",
        },
        {
            "timestamp": "2026-10-17T07:34:12+00:00",
            "service": "ecommerce-payment-gateway",
            "operation": "GET /missing-duration",
        },
    ],
    "correlations": [],
}

INC0069_INCIDENT = {
    "service": "ecommerce-payment-gateway",
    "start_time": "2026-10-17T07:34:01.627452Z",
    "end_time": "2026-10-17T07:34:46.916488Z",
}


def test_inc0069_trace_ranking_uses_stored_spans_only():
    result = trace_answer(INC0069_INCIDENT, INC0069_EVIDENCE)
    assert "GET /health" in result["answer"]
    assert "61.028" in result["answer"]
    assert "327efbd6b0fa595bdac1c58f8b76220e" in result["answer"]
    assert "POST /checkout" not in result["answer"]
    assert "9999" not in result["answer"]
    assert "missing duration_ms" in result["answer"]
    assert "parent_span_id was not stored" in result["answer"]
    assert result["evidence_refs"][0] == {"source": "traces", "index": 0, "label": "GET /health"}


def test_inc0069_cpu_value_is_cores_not_saturation():
    result = metric_answer(INC0069_INCIDENT, INC0069_EVIDENCE)
    assert "0.5333326945106098" in result["answer"]
    assert "cores" in result["answer"]
    assert "not a percentage" in result["answer"]
    assert "saturation is not established" in result["answer"].lower()
    assert "container_cpu_cfs_throttled_seconds_total" in result["answer"]
    assert result["evidence_refs"][0]["source"] == "metrics"
    assert result["evidence_refs"][0]["index"] == 1


def test_inc0069_operator_request_is_not_treated_as_the_cause():
    result = causal_answer(INC0069_INCIDENT, INC0069_EVIDENCE)
    assert "not causation" in result["answer"].lower() or "Temporal order is not causation" in result["answer"]
    assert "/internal/faults/apply" in result["answer"]
    assert "not confirmed" in result["answer"].lower()
    assert "configuration" in result["answer"].lower()
    assert any(ref["source"] == "logs" and ref["index"] == 0 for ref in result["evidence_refs"])


def test_hypothesis_ranking_does_not_invent_a_third_cause():
    result = hypothesis_answer(
        INC0069_INCIDENT,
        {"alternative_explanations": ["A traffic surge.", "A configuration change.", "A memory leak."]},
        INC0069_EVIDENCE,
    )
    assert "No extra hypothesis is added" in result["answer"]
    assert "memory leak" not in result["answer"].lower()
    assert "contradicted" in result["answer"].lower()
    assert result["certainty"] == "hypothesis"


def test_a_cause_question_is_not_answered_as_a_metric_definition():
    assert classify_question("Did the earlier operator request cause the CPU increase?") == "causal"
    assert classify_question("What does cpu_usage 0.5333 mean?") == "metrics"


def test_stored_rows_keep_trace_fields():
    grouped = rows_from_stored(
        [
            {
                "source": "jaeger",
                "service": "ecommerce-payment-gateway",
                "timestamp": "2026-10-17T07:34:15.122459+00:00",
                "event_type": "trace",
                "severity": "info",
                "content": "Span GET /health",
                "metadata": {
                    "operation": "GET /health",
                    "duration_ms": 61.028,
                    "trace_id": "327efbd6b0fa595bdac1c58f8b76220e",
                    "span_id": "5a986d5d935fc237",
                    "tags": {"http.route": "/health"},
                },
            }
        ]
    )
    span = grouped["traces"][0]
    assert span["duration_ms"] == 61.028
    assert span["trace_id"] == "327efbd6b0fa595bdac1c58f8b76220e"
    assert span["parent_span_id"] is None
    assert "duration_ms=61.028" in evidence_brief(grouped)
