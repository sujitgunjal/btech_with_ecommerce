"""Investigation engine — orchestrates the full RAG + LLM pipeline.

Pipeline:
1. Preprocess and format collected evidence.
2. Generate a semantic query from evidence and incident metadata.
3. Retrieve similar historical incidents from ChromaDB.
4. Build the investigation context.
5. Construct the LLM prompt.
6. Call the LLM for root cause analysis.
7. Validate and return structured RCA.

Graceful degradation:
- If ChromaDB is unreachable, the pipeline continues without history.
- If the LLM is unconfigured or fails, a partial result is returned.
- If no evidence was collected, the RCA notes insufficient data.
"""

import logging
from typing import Any

from ..rag.documents import build_semantic_query, format_evidence_for_llm
from ..rag.retriever import IncidentRetriever
from .context import InvestigationContext, build_investigation_context
from .llm import LLMClient
from .prompt import build_system_prompt, build_user_prompt

logger = logging.getLogger("incident-backend")


class InvestigationEngine:
    """Runs the end-to-end investigation pipeline for a single incident."""

    def __init__(self) -> None:
        self._llm = LLMClient()

    async def investigate(
        self,
        incident: Any,
        evidence_rows: list,
    ) -> dict[str, Any]:
        """Execute the full investigation pipeline.

        Args:
            incident: The Incident ORM object.
            evidence_rows: List of Evidence ORM rows (excluding collector_error).

        Returns:
            A validated RCA dict matching the RootCauseAnalysis schema.
        """
        service = getattr(incident, "service", "unknown")
        logger.info(
            "Starting investigation engine for incident_id=%s service=%s evidence=%d",
            incident.id,
            service,
            len(evidence_rows),
        )

        # ------------------------------------------------------------------
        # 1. Format evidence for the LLM prompt
        # ------------------------------------------------------------------
        evidence_formatted = format_evidence_for_llm(evidence_rows)

        # ------------------------------------------------------------------
        # 2. Generate semantic query from evidence
        # ------------------------------------------------------------------
        semantic_query = build_semantic_query(incident, evidence_rows)

        # ------------------------------------------------------------------
        # 3. Retrieve similar historical incidents
        # ------------------------------------------------------------------
        historical_incidents = self._retrieve_historical(semantic_query)

        # ------------------------------------------------------------------
        # 4. Build investigation context
        # ------------------------------------------------------------------
        context = build_investigation_context(
            incident=incident,
            evidence_formatted=evidence_formatted,
            historical_incidents=historical_incidents,
            semantic_query=semantic_query,
            evidence_count=len(evidence_rows),
        )

        # ------------------------------------------------------------------
        # 5-7. Generate RCA via LLM
        # ------------------------------------------------------------------
        rca = await self._generate_rca(context)

        logger.info(
            "Investigation engine completed for incident_id=%s confidence=%.2f",
            incident.id,
            rca.get("confidence", 0.0),
        )
        return rca

    def _retrieve_historical(self, query: str) -> list[dict[str, Any]]:
        """Retrieve similar historical incidents, degrading on failure."""
        try:
            retriever = IncidentRetriever()
            return retriever.retrieve(query)
        except Exception as exc:
            logger.warning(
                "Historical retrieval failed (continuing without history): %s",
                exc,
            )
            return []

    async def _generate_rca(
        self, context: InvestigationContext
    ) -> dict[str, Any]:
        """Build prompt, call LLM, and return validated RCA."""
        if not self._llm.is_configured:
            logger.warning("LLM is not configured — returning evidence-only RCA")
            return self._build_fallback_rca(context)

        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(
            incident=context.incident,
            evidence_formatted=context.evidence_formatted,
            historical_incidents=context.historical_incidents,
        )

        try:
            rca = await self._llm.generate_rca(system_prompt, user_prompt)

            if context.historical_incidents and not rca.get(
                "relevant_historical_incidents"
            ):
                rca["relevant_historical_incidents"] = [
                    {
                        "incident_id": h["incident_id"],
                        "incident_type": h.get("metadata", {}).get(
                            "incident_type", ""
                        ),
                        "similarity_score": h.get("similarity_score", 0.0),
                        "relevance": "Retrieved via semantic similarity",
                    }
                    for h in context.historical_incidents
                ]
            return rca

        except Exception as exc:
            logger.error("LLM RCA generation failed: %s", exc)
            return self._build_fallback_rca(context, error=str(exc))

    @staticmethod
    def _build_fallback_rca(
        context: InvestigationContext,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Build a minimal RCA when the LLM is unavailable or fails."""
        service = getattr(context.incident, "service", "unknown")
        severity = getattr(context.incident, "severity", "unknown")

        if not context.has_evidence:
            root_cause = (
                "Unable to determine root cause — no observability evidence "
                "was collected from Prometheus, Loki, or Jaeger."
            )
            confidence = 0.0
        else:
            root_cause = (
                "Automated root cause analysis is unavailable. "
                "Evidence has been collected and is available for manual review."
            )
            confidence = 0.1

        fallback: dict[str, Any] = {
            "root_cause": root_cause,
            "supporting_evidence": [],
            "affected_services": [service],
            "confidence": confidence,
            "timeline": [],
            "alternative_explanations": [],
            "recommended_actions": [
                "Review the collected evidence manually.",
                f"Check {service} health and recent deployments.",
            ],
            "relevant_historical_incidents": [
                {
                    "incident_id": h["incident_id"],
                    "incident_type": h.get("metadata", {}).get(
                        "incident_type", ""
                    ),
                    "similarity_score": h.get("similarity_score", 0.0),
                    "relevance": "Retrieved via semantic similarity",
                }
                for h in context.historical_incidents
            ],
        }

        if error:
            fallback["analysis_error"] = error

        return fallback
