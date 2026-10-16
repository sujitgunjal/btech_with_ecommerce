import json
import logging
from datetime import datetime
from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.evidence import EvidenceResponse, UnifiedEvidenceResponse
from ..schemas.incident import (
    IncidentCreate,
    IncidentDeleteAllResponse,
    IncidentListResponse,
    IncidentResponse,
    IncidentUpdate,
)
from ..schemas.investigation import InvestigationResponse
from ..services.evidence_service import EvidenceService
from ..services.incident_service import IncidentService, find_incident_scenario
from ..services.investigation_service import InvestigationService

logger = logging.getLogger("incident-backend")

router = APIRouter()


@router.post("", response_model=IncidentResponse, status_code=201)
def create_incident(
    incident_data: IncidentCreate,
    db: Session = Depends(get_db),
):
    """Create a new incident."""
    svc = IncidentService(db)
    incident = svc.create(incident_data)
    logger.info(
        "Incident created id=%s external_id=%s",
        incident.id,
        incident.external_id,
    )
    return incident


@router.get("", response_model=IncidentListResponse)
def list_incidents(
    status: Optional[str] = Query(None),
    service: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List incidents with optional filters."""
    svc = IncidentService(db)
    incidents = svc.list_incidents(status=status, service=service, severity=severity)
    return IncidentListResponse(incidents=incidents, total=len(incidents))


@router.delete("", response_model=IncidentDeleteAllResponse)
def delete_all_incidents(db: Session = Depends(get_db)):
    """Delete every stored incident, including investigations and evidence."""
    svc = IncidentService(db)
    deleted = svc.delete_all()
    logger.info("All incidents deleted count=%s", deleted)
    return IncidentDeleteAllResponse(deleted=deleted)


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(
    incident_id: str,
    db: Session = Depends(get_db),
):
    """Get a single incident by ID or external ID."""
    svc = IncidentService(db)
    incident = svc.get_by_identifier(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident



@router.patch("/{incident_id}", response_model=IncidentResponse)
def update_incident(
    incident_id: int,
    update_data: IncidentUpdate,
    db: Session = Depends(get_db),
):
    """Partially update an incident."""
    svc = IncidentService(db)
    incident = svc.update(incident_id, update_data)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    logger.info("Incident updated id=%s", incident_id)
    return incident


@router.post(
    "/{incident_id}/resolve", response_model=IncidentResponse
)
def resolve_incident(
    incident_id: int,
    db: Session = Depends(get_db),
):
    """Mark an incident as resolved."""
    svc = IncidentService(db)
    incident = svc.resolve(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    logger.info("Incident resolved id=%s", incident_id)
    return incident


@router.post(
    "/{incident_id}/investigate",
    response_model=InvestigationResponse,
)
async def investigate_incident(
    incident_id: int,
    db: Session = Depends(get_db),
):
    """Trigger an investigation for an incident."""
    svc = IncidentService(db)
    incident = svc.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    inv_svc = InvestigationService(db)
    investigation = await inv_svc.start_investigation(incident)
    evidence_count = inv_svc.count_evidence(incident.id)

    logger.info(
        "Investigation completed id=%s incident_id=%s status=%s",
        investigation.id,
        incident_id,
        investigation.status,
    )

    report_data = _parse_report(investigation.report)

    return InvestigationResponse(
        id=investigation.id,
        incident_id=investigation.incident_id,
        status=investigation.status,
        started_at=investigation.started_at,
        completed_at=investigation.completed_at,
        report=report_data,
        confidence=investigation.confidence,
        created_at=investigation.created_at,
        evidence_count=evidence_count,
    )


@router.get(
    "/{incident_id}/evidence",
    response_model=Union[UnifiedEvidenceResponse, list[EvidenceResponse]],
)
async def get_incident_evidence(
    incident_id: str,
    start_time: Optional[datetime] = Query(None, description="Optional override start time"),
    end_time: Optional[datetime] = Query(None, description="Optional override end time"),
    format: Optional[str] = Query(None, description="Set to 'raw' or 'legacy' for DB rows"),
    db: Session = Depends(get_db),
):
    """Obtain unified telemetry evidence (logs, metrics, traces) for an incident.

    Automatically resolves the affected service and relevant time window from
    the incident data (database or scenario library).
    """
    svc = IncidentService(db)
    incident = svc.get_by_identifier(incident_id)

    # Legacy raw format request
    if format in ("raw", "legacy", "db"):
        if incident is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        return svc.get_evidence(incident.id)

    service: str
    target_start: datetime | str
    target_end: datetime | str | None
    resolved_id: str

    if incident is not None:
        service = incident.service
        target_start = start_time or incident.start_time
        target_end = end_time or incident.end_time
        resolved_id = incident.external_id or f"INC-{incident.id:04d}"
    else:
        scenario = find_incident_scenario(incident_id)
        if scenario is not None:
            service = scenario["service"]
            target_start = start_time or scenario["start_time"]
            target_end = end_time or scenario["end_time"]
            resolved_id = scenario["incident_id"]
        else:
            raise HTTPException(
                status_code=404, detail=f"Incident '{incident_id}' not found"
            )

    evidence_svc = EvidenceService()
    return await evidence_svc.get_incident_evidence(
        incident_id=resolved_id,
        service=service,
        start_time=target_start,
        end_time=target_end,
    )


def _parse_report(report_value: str | None) -> dict | None:
    """Deserialize a JSON report string from the DB into a dict."""
    if report_value is None:
        return None
    try:
        return json.loads(report_value)
    except (json.JSONDecodeError, TypeError):
        return {"raw": report_value}

