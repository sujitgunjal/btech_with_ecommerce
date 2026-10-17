from types import SimpleNamespace

from app.investigation.diagnosis import refine_rca, sanitize_operator_text
from app.investigation.prompt import build_user_prompt


MEMORY_EVIDENCE = """
### Metrics
memory_usage peak=812.4
### Logs
container memory working set elevated
"""

PAYMENT_EVIDENCE = """
### Logs
http request failed method=POST path=/checkout status=504 duration_ms=2168.0
### Traces
Span POST /charges duration=3004.5ms
payment gateway timeout
### Correlations
Trace shared by ecommerce-shop-api and ecommerce-payment-gateway. Causation is not established.
"""


def test_memory_diagnosis_does_not_repeat_the_experiment():
    rca = refine_rca(
        {
            "root_cause": "An intentional memory_pressure experiment caused increased memory usage.",
            "supporting_evidence": ["memory_pressure was injected"],
            "affected_services": ["ecommerce-shop-api"],
            "confidence": 0.95,
            "timeline": [{"timestamp": "", "event": "Started the memory_pressure experiment"}],
            "alternative_explanations": ["The memory_pressure fault was still running"],
            "recommended_actions": [
                "Stop the memory_pressure experiment.",
                "Restart the service.",
            ],
            "relevant_historical_incidents": [],
        },
        MEMORY_EVIDENCE,
    )
    text = " ".join(
        [
            rca["root_cause"],
            *rca["recommended_actions"],
            *rca["alternative_explanations"],
            *(item["event"] for item in rca["timeline"]),
        ]
    ).lower()
    assert "memory_pressure" not in text
    assert "experiment" not in text
    assert "confirmed" in rca["root_cause"].lower()
    assert "not established" in rca["root_cause"].lower()
    assert any("memory" in action.lower() and "limit" in action.lower() for action in rca["recommended_actions"])
    assert not any("restart" in action.lower() for action in rca["recommended_actions"])
    assert rca["confidence"] <= 0.55


def test_payment_actions_compare_latency_and_errors():
    rca = refine_rca(
        {
            "root_cause": "The payment_timeout fault made checkout fail.",
            "supporting_evidence": [],
            "affected_services": ["ecommerce-shop-api"],
            "confidence": 0.4,
            "timeline": [],
            "alternative_explanations": [],
            "recommended_actions": ["Remove the injected fault and restart the shop."],
            "relevant_historical_incidents": [],
        },
        PAYMENT_EVIDENCE,
    )
    joined = " ".join(rca["recommended_actions"]).lower()
    assert "payment_timeout" not in joined
    assert "injected" not in joined
    assert "latency" in joined
    assert "error rate" in joined
    assert "restart" not in joined


def test_restart_remains_when_the_service_is_still_down():
    rca = refine_rca(
        {
            "root_cause": "The service is unavailable.",
            "supporting_evidence": [],
            "affected_services": ["ecommerce-shop-api"],
            "confidence": 0.4,
            "timeline": [],
            "alternative_explanations": [],
            "recommended_actions": ["Restart the service."],
            "relevant_historical_incidents": [],
        },
        "health check failed\nconnection refused\nstatus=503",
    )
    assert any("restart" in action.lower() for action in rca["recommended_actions"])
    assert "not established" in rca["root_cause"].lower()


def test_empty_evidence_stays_a_hypothesis():
    rca = refine_rca(
        {
            "root_cause": "An intentional cpu_high experiment saturated the processor.",
            "supporting_evidence": [],
            "affected_services": ["ecommerce-shop-api"],
            "confidence": 0.9,
            "timeline": [],
            "alternative_explanations": [],
            "recommended_actions": ["Disable fault injection."],
            "relevant_historical_incidents": [],
        },
        "",
    )
    assert rca["root_cause"].lower().startswith("hypothesis")
    assert "cpu_high" not in rca["root_cause"]
    assert rca["confidence"] <= 0.55
    assert any("do not justify a restart" in action.lower() for action in rca["recommended_actions"])


def test_prompt_hides_scenario_identifiers():
    incident = SimpleNamespace(
        title="memory_pressure on ecommerce-shop-api",
        service="ecommerce-shop-api",
        severity="high",
        description="A fault experiment (memory_pressure) is active on ecommerce-shop-api.",
        start_time="2026-10-16T13:00:00Z",
        end_time="2026-10-16T13:05:00Z",
    )
    prompt = build_user_prompt(
        incident,
        {"evidence_stats": "", "evidence_text": "memory working set elevated"},
        [{"incident_id": "INC-005", "similarity_score": 0.8, "metadata": {"incident_type": "memory_pressure"}, "document": ""}],
    )
    assert "memory_pressure" not in prompt
    assert "fault experiment" not in prompt.lower()
    assert sanitize_operator_text("payment_timeout") == "the observed condition"
