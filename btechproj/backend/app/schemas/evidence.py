"""Pydantic schemas for evidence and the common telemetry model."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class NormalizedEvent(BaseModel):
    """Common telemetry schema used across all collectors.

    All collectors convert their source-specific data into this
    unified representation before storage.
    """

    timestamp: datetime
    source: Literal["prometheus", "loki", "jaeger", "deployment", "git", "correlation"]
    service: str
    event_type: str
    severity: Literal["info", "warning", "error", "critical"]
    content: str
    metadata: dict = Field(default_factory=dict)


class EvidenceResponse(BaseModel):
    """Schema for evidence API responses."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    incident_id: int
    source: str
    service: Optional[str] = None
    timestamp: Optional[datetime] = None
    event_type: str
    severity: str
    content: str
    metadata: Optional[dict] = Field(
        default_factory=dict, validation_alias="metadata_"
    )
    created_at: datetime


class TimeWindow(BaseModel):
    """Time window for unified incident evidence."""

    start: str
    end: str


class UnifiedEvidenceResponse(BaseModel):
    """Unified evidence response schema combining logs, metrics, and traces."""

    incident_id: str
    service: str
    time_window: TimeWindow
    logs: list[dict] = Field(default_factory=list)
    metrics: list[dict] = Field(default_factory=list)
    traces: list[dict] = Field(default_factory=list)
    correlations: list[dict] = Field(default_factory=list)

