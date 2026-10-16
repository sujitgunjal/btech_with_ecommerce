"""Investigation context builder.

Combines current incident evidence with historically retrieved incidents
into a structured context ready for prompt construction and LLM reasoning.
"""

import logging
from typing import Any

logger = logging.getLogger("incident-backend")


class InvestigationContext:
    """Immutable container holding all context for a single investigation."""

    def __init__(
        self,
        incident: Any,
        evidence_formatted: dict[str, str],
        historical_incidents: list[dict[str, Any]],
        semantic_query: str,
        evidence_count: int,
    ) -> None:
        self.incident = incident
        self.evidence_formatted = evidence_formatted
        self.historical_incidents = historical_incidents
        self.semantic_query = semantic_query
        self.evidence_count = evidence_count

    @property
    def has_evidence(self) -> bool:
        return self.evidence_count > 0

    @property
    def has_historical_context(self) -> bool:
        return len(self.historical_incidents) > 0

    def summary(self) -> str:
        """Return a short human-readable summary of the context."""
        return (
            f"Investigation context for incident on {getattr(self.incident, 'service', '?')}: "
            f"{self.evidence_count} evidence items, "
            f"{len(self.historical_incidents)} historical matches"
        )


def build_investigation_context(
    incident: Any,
    evidence_formatted: dict[str, str],
    historical_incidents: list[dict[str, Any]],
    semantic_query: str,
    evidence_count: int,
) -> InvestigationContext:
    """Construct an InvestigationContext from the pipeline outputs."""
    ctx = InvestigationContext(
        incident=incident,
        evidence_formatted=evidence_formatted,
        historical_incidents=historical_incidents,
        semantic_query=semantic_query,
        evidence_count=evidence_count,
    )
    logger.info("Built investigation context: %s", ctx.summary())
    return ctx
