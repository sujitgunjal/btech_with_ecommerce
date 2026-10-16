"""Quick local test for all investigation pipeline components.

Run from backend/ with: python -m scripts.test_components
Does NOT require Docker or API — tests modules directly.
"""

import sys
sys.path.insert(0, ".")

def main():
    # Test 1: Imports
    print("Test 1: Importing investigation modules...")
    from app.schemas.investigation import (
        RootCauseAnalysis, InvestigationResponse, TimelineEntry, HistoricalIncidentRef,
    )
    print("  OK: Schemas imported")

    from app.rag.documents import format_evidence_for_llm, build_semantic_query
    from app.rag.retriever import IncidentRetriever
    print("  OK: RAG modules imported")

    from app.investigation.engine import InvestigationEngine
    from app.investigation.llm import LLMClient
    from app.investigation.context import InvestigationContext, build_investigation_context
    from app.investigation.prompt import build_system_prompt, build_user_prompt
    print("  OK: Investigation modules imported")

    # Test 2: Schema validation
    print("\nTest 2: RCA schema validation...")
    rca = RootCauseAnalysis(
        root_cause="Database connection pool exhausted",
        supporting_evidence=["Connection timeout errors in logs", "HTTP 500 spike in metrics"],
        affected_services=["order-service", "postgres"],
        confidence=0.85,
        timeline=[TimelineEntry(timestamp="2026-09-21T09:00:00Z", event="Connection failures begin")],
        alternative_explanations=["Network partition"],
        recommended_actions=["Restart connection pool", "Check postgres health"],
        relevant_historical_incidents=[
            HistoricalIncidentRef(
                incident_id="INC-001", incident_type="database_failure",
                similarity_score=0.9, relevance="Similar symptoms",
            )
        ],
    )
    print(f"  OK: RCA validated, confidence={rca.confidence}")
    rca_dict = rca.model_dump()
    print(f"  OK: Serialized to dict, fields={len(rca_dict)}")

    # Test 3: Prompt generation
    print("\nTest 3: Prompt generation...")
    system_prompt = build_system_prompt()
    print(f"  OK: System prompt length={len(system_prompt)}")
    assert "JSON" in system_prompt
    assert "root_cause" in system_prompt
    print("  OK: System prompt contains required schema")

    # Test 4: Semantic retrieval
    print("\nTest 4: Semantic retrieval from ChromaDB...")
    retriever = IncidentRetriever()

    test_queries = [
        "database connection failure in order service",
        "CPU usage spike in container",
        "slow response times and high latency",
        "deployment caused errors",
    ]
    for query in test_queries:
        results = retriever.retrieve(query)
        ids = [r["incident_id"] for r in results]
        scores = [f"{r['similarity_score']:.3f}" for r in results]
        print(f"  Query: '{query[:50]}...' -> {ids} (scores: {scores})")

    # Test 5: LLM client configuration check
    print("\nTest 5: LLM client...")
    llm = LLMClient()
    print(f"  Configured: {llm.is_configured}")
    print(f"  Model: {llm.model}")

    # Test 6: LLM response parsing
    print("\nTest 6: LLM response parsing...")
    import json
    sample_response = json.dumps({
        "root_cause": "PostgreSQL became unavailable",
        "supporting_evidence": ["Connection errors in logs"],
        "affected_services": ["postgres", "order-service"],
        "confidence": 0.82,
        "timeline": [{"timestamp": "09:00", "event": "DB went down"}],
        "alternative_explanations": ["Network issue"],
        "recommended_actions": ["Restart postgres"],
        "relevant_historical_incidents": [
            {"incident_id": "INC-001", "incident_type": "database_failure",
             "similarity_score": 0.9, "relevance": "Same pattern"}
        ],
    })
    parsed = LLMClient._parse_response(sample_response)
    assert parsed["root_cause"] == "PostgreSQL became unavailable"
    assert parsed["confidence"] == 0.82
    assert len(parsed["affected_services"]) == 2
    print("  OK: Sample LLM response parsed and validated")

    # Test 7: Context builder
    print("\nTest 7: Context builder...")

    class MockIncident:
        id = 1
        service = "order-service"
        title = "Test incident"
        description = "Testing"
        severity = "high"
        start_time = "2026-09-21T09:00:00Z"
        end_time = "2026-09-21T09:15:00Z"

    evidence_formatted = {
        "logs_summary": "Error logs detected",
        "metrics_summary": "HTTP 500 rate increased",
        "traces_summary": "Failed spans",
        "evidence_stats": "Evidence: 10 logs, 5 metrics, 3 traces",
        "evidence_text": "Combined evidence text",
    }

    ctx = build_investigation_context(
        incident=MockIncident(),
        evidence_formatted=evidence_formatted,
        historical_incidents=results,
        semantic_query="test query",
        evidence_count=18,
    )
    assert ctx.has_evidence
    assert ctx.has_historical_context
    print(f"  OK: {ctx.summary()}")

    # Test 8: Full prompt construction
    print("\nTest 8: Full prompt construction...")
    user_prompt = build_user_prompt(
        incident=MockIncident(),
        evidence_formatted=evidence_formatted,
        historical_incidents=results,
    )
    print(f"  OK: User prompt length={len(user_prompt)}")
    assert "order-service" in user_prompt
    assert "Evidence" in user_prompt
    print("  OK: User prompt contains incident and evidence")

    print("\n" + "=" * 60)
    print("ALL COMPONENT TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
