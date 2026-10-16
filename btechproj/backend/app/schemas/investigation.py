"""Pydantic schemas for investigation and root cause analysis."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class TimelineEntry(BaseModel):
    """A single event in the investigation timeline."""

    timestamp: str = ""
    event: str


class HistoricalIncidentRef(BaseModel):
    """Reference to a similar historical incident found via RAG."""

    incident_id: str
    incident_type: str = ""
    similarity_score: float = 0.0
    relevance: str = ""


class RootCauseAnalysis(BaseModel):
    """Structured root cause analysis produced by the LLM."""

    root_cause: str
    supporting_evidence: list[str] = Field(default_factory=list)
    affected_services: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    timeline: list[TimelineEntry] = Field(default_factory=list)
    alternative_explanations: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    relevant_historical_incidents: list[HistoricalIncidentRef] = Field(
        default_factory=list
    )


class InvestigationResponse(BaseModel):
    """Schema for investigation API responses."""

    id: int
    incident_id: int
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    report: Optional[dict[str, Any]] = None
    confidence: Optional[float] = None
    created_at: datetime
    evidence_count: int = 0
