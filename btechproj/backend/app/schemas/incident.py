"""Pydantic schemas for incident endpoints."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class IncidentCreate(BaseModel):
    """Schema for creating a new incident."""

    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    service: str = Field(min_length=1, max_length=100)
    severity: Literal["low", "medium", "high", "critical"]
    start_time: datetime
    end_time: Optional[datetime] = None
    p99_latency_ms: Optional[float] = None
    error_rate: Optional[float] = None
    captured_at: Optional[datetime] = None


class IncidentUpdate(BaseModel):
    """Schema for updating an existing incident."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    description: Optional[str] = None
    service: Optional[str] = Field(default=None, min_length=1, max_length=100)
    severity: Optional[Literal["low", "medium", "high", "critical"]] = None
    status: Optional[
        Literal["created", "investigating", "resolved", "failed"]
    ] = None
    end_time: Optional[datetime] = None
    p99_latency_ms: Optional[float] = None
    error_rate: Optional[float] = None
    captured_at: Optional[datetime] = None


class IncidentResponse(BaseModel):
    """Schema for incident API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    title: str
    description: Optional[str] = None
    service: str
    severity: str
    status: str
    start_time: datetime
    end_time: Optional[datetime] = None
    p99_latency_ms: Optional[float] = None
    error_rate: Optional[float] = None
    captured_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class IncidentListResponse(BaseModel):
    """Schema for paginated incident list responses."""

    incidents: list[IncidentResponse]
    total: int


class IncidentDeleteAllResponse(BaseModel):
    """Schema for deleting every stored incident."""

    deleted: int
