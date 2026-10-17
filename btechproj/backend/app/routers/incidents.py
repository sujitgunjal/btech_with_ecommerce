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
from ..schemas.investigation import IncidentAnswer, IncidentQuestion, InvestigationResponse
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


@router.post("/{incident_id}/ask", response_model=IncidentAnswer)
async def ask_about_incident(
    incident_id: int,
    body: IncidentQuestion,
    db: Session = Depends(get_db),
):
    """Answer a question from the incident's existing RCA and telemetry."""
    from ..incident_chat import (
        build_chat_messages,
        evidence_brief,
        fallback_answer,
        grounded_answer,
        parse_model_answer,
        rows_from_stored,
    )
    from ..investigation.llm import LLMClient
    from ..models.investigation import Investigation
    from ..services.evidence_service import EvidenceService

    incident = IncidentService(db).get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    investigation = (
        db.query(Investigation)
        .filter(Investigation.incident_id == incident.id)
        .order_by(Investigation.id.desc())
        .first()
    )
    report = _parse_report(investigation.report) if investigation and investigation.report else None
    stored = rows_from_stored(
        [
            {
                "source": row.source,
                "service": row.service,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "event_type": row.event_type,
                "severity": row.severity,
                "content": row.content,
                "metadata": row.metadata_ or {},
            }
            for row in IncidentService(db).get_evidence(incident.id)
        ]
    )
    if any(stored[name] for name in ("logs", "metrics", "traces")):
        evidence_lists = stored
    else:
        evidence = await EvidenceService().get_incident_evidence(
            incident_id=incident.external_id or str(incident.id),
            service=incident.service,
            start_time=incident.start_time,
            end_time=incident.end_time,
        )
        evidence_lists = {
            "logs": evidence.get("logs") or [],
            "metrics": evidence.get("metrics") or [],
            "traces": evidence.get("traces") or [],
            "correlations": evidence.get("correlations") or [],
        }
    evidence_text = evidence_brief(evidence_lists)
    incident_view = {
        "service": incident.service,
        "severity": incident.severity,
        "title": incident.title,
        "description": incident.description,
        "start_time": incident.start_time,
        "end_time": incident.end_time,
    }
    grounded = grounded_answer(body.question, incident_view, report, evidence_lists)
    if grounded is not None:
        return IncidentAnswer(**grounded)
    if not report and not evidence_text.strip():
        result = fallback_answer(body.question, None, "")
        return IncidentAnswer(**result)

    messages = build_chat_messages(
        question=body.question,
        history=[turn.model_dump() for turn in body.history],
        incident=incident_view,
        report=report,
        evidence_text=evidence_text,
        historical_note=_historical_note(incident, body.question),
    )
    try:
        raw = await LLMClient().complete(messages)
        result = parse_model_answer(raw, evidence_lists)
    except Exception as exc:
        logger.warning("Incident question fell back without the model: %s", exc)
        result = fallback_answer(body.question, report, evidence_text)
    return IncidentAnswer(**result)


def _historical_note(incident, question: str) -> str:
    """Reuse the existing RAG retriever. Matches are context, not proof."""
    try:
        from ..rag.retriever import IncidentRetriever

        matches = IncidentRetriever().retrieve(
            f"{incident.service} {incident.title or ''} {question}",
            top_k=3,
        )
    except Exception as exc:
        logger.warning("Historical retrieval skipped for incident question: %s", exc)
        return ""
    return "; ".join(
        f"{item.get('incident_id')} similarity={item.get('similarity_score')} context only"
        for item in matches
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

