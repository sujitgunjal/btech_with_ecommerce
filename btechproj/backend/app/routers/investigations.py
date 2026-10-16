"""Investigation endpoints."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.evidence import EvidenceResponse
from ..schemas.investigation import InvestigationResponse
from ..services.investigation_service import InvestigationService

logger = logging.getLogger("incident-backend")

router = APIRouter()


@router.get("/{investigation_id}", response_model=InvestigationResponse)
def get_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
):
    """Get a single investigation by ID."""
    inv_svc = InvestigationService(db)
    investigation = inv_svc.get(investigation_id)
    if investigation is None:
        raise HTTPException(
            status_code=404, detail="Investigation not found"
        )

    evidence_count = inv_svc.count_evidence(investigation.incident_id)

    report_data = None
    if investigation.report:
        try:
            report_data = json.loads(investigation.report)
        except (json.JSONDecodeError, TypeError):
            report_data = {"raw": investigation.report}

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
    "/{investigation_id}/evidence",
    response_model=list[EvidenceResponse],
)
def get_investigation_evidence(
    investigation_id: int,
    db: Session = Depends(get_db),
):
    """List all evidence associated with an investigation."""
    inv_svc = InvestigationService(db)
    evidence = inv_svc.get_evidence_for_investigation(investigation_id)
    if evidence is None:
        raise HTTPException(
            status_code=404, detail="Investigation not found"
        )
    return evidence
