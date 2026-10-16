"""Business logic for incident management."""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..models.evidence import Evidence
from ..models.incident import Incident
from ..models.investigation import Investigation
from ..schemas.incident import IncidentCreate, IncidentUpdate

logger = logging.getLogger("incident-backend")


class IncidentService:
    """Service layer for incident CRUD operations."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, data: IncidentCreate) -> Incident:
        """Create a new incident with auto-generated external_id."""
        incident = Incident(
            external_id="PENDING",  # placeholder, replaced after insert
            title=data.title,
            description=data.description,
            service=data.service,
            severity=data.severity,
            status="created",
            start_time=data.start_time,
            end_time=data.end_time,
            p99_latency_ms=data.p99_latency_ms,
            error_rate=data.error_rate,
            captured_at=data.captured_at or data.start_time,
        )
        self.db.add(incident)
        self.db.commit()
        self.db.refresh(incident)

        # Generate external_id from the auto-incremented primary key
        incident.external_id = f"INC-{incident.id:04d}"
        self.db.commit()
        self.db.refresh(incident)

        return incident

    def get(self, incident_id: int) -> Incident | None:
        """Get a single incident by ID."""
        return (
            self.db.query(Incident)
            .filter(Incident.id == incident_id)
            .first()
        )

    def get_by_identifier(self, identifier: str | int) -> Incident | None:
        """Find an incident by primary key, external_id, or normalized ID."""
        if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
            inc = self.get(int(identifier))
            if inc:
                return inc

        str_id = str(identifier).strip()
        # Direct external_id lookup
        inc = (
            self.db.query(Incident)
            .filter(Incident.external_id == str_id)
            .first()
        )
        if inc:
            return inc

        # Normalized lookup (e.g. INC-001 vs INC-0001)
        if str_id.upper().startswith("INC-"):
            num_str = str_id[4:].lstrip("0")
            if num_str.isdigit():
                num = int(num_str)
                candidates = [f"INC-{num:03d}", f"INC-{num:04d}", f"INC-{num}"]
                inc = (
                    self.db.query(Incident)
                    .filter(Incident.external_id.in_(candidates))
                    .first()
                )
                if inc:
                    return inc
                inc = self.get(num)
                if inc:
                    return inc

        return None


    def list_incidents(
        self,
        status: Optional[str] = None,
        service: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> list[Incident]:
        """List incidents with optional filters."""
        query = self.db.query(Incident)

        if status:
            query = query.filter(Incident.status == status)
        if service:
            query = query.filter(Incident.service == service)
        if severity:
            query = query.filter(Incident.severity == severity)

        return query.order_by(Incident.created_at.desc()).all()

    def update(
        self, incident_id: int, data: IncidentUpdate
    ) -> Incident | None:
        """Update an existing incident."""
        incident = self.get(incident_id)
        if incident is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(incident, field, value)

        incident.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(incident)
        return incident

    def resolve(self, incident_id: int) -> Incident | None:
        """Mark an incident as resolved."""
        incident = self.get(incident_id)
        if incident is None:
            return None

        incident.status = "resolved"
        incident.end_time = incident.end_time or datetime.now(timezone.utc)
        incident.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(incident)
        return incident

    def delete_all(self) -> int:
        """Delete every incident and its stored investigations and evidence."""
        count = self.db.query(Incident).count()
        self.db.query(Evidence).delete(synchronize_session=False)
        self.db.query(Investigation).delete(synchronize_session=False)
        self.db.query(Incident).delete(synchronize_session=False)
        self.db.commit()
        logger.info("Deleted all incidents count=%d", count)
        return count

    def get_evidence(self, incident_id: int) -> list[Evidence]:
        """Get all evidence for an incident."""
        return (
            self.db.query(Evidence)
            .filter(Evidence.incident_id == incident_id)
            .order_by(Evidence.timestamp.asc())
            .all()
        )


def find_incident_scenario(incident_id: str | int) -> dict | None:
    """Find scenario metadata (service, start_time, end_time) from scenario.json files.

    IMPORTANT: This only returns the operational fields needed for telemetry collection.
    It NEVER returns expected_root_cause or ground truth!
    """
    import json
    from pathlib import Path

    str_id = str(incident_id).strip().upper()
    candidate_ids = {str_id}
    if str_id.startswith("INC-"):
        num_str = str_id[4:].lstrip("0")
        if num_str.isdigit():
            num = int(num_str)
            candidate_ids.add(f"INC-{num:03d}")
            candidate_ids.add(f"INC-{num:04d}")
            candidate_ids.add(str(num))
    elif str_id.isdigit():
        num = int(str_id)
        candidate_ids.add(f"INC-{num:03d}")
        candidate_ids.add(f"INC-{num:04d}")

    possible_roots = [
        Path.cwd() / "incidents",
        Path(__file__).resolve().parents[3] / "incidents",
        Path(__file__).resolve().parents[2] / "incidents",
        Path("/incidents"),
    ]
    for root in possible_roots:
        if root.exists():
            for scenario_path in root.glob("*/scenario.json"):
                try:
                    with open(scenario_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("incident_id") in candidate_ids:
                        return {
                            "incident_id": data.get("incident_id"),
                            "service": data.get("affected_service"),
                            "start_time": data.get("start_time"),
                            "end_time": data.get("end_time"),
                        }
                except Exception:
                    continue
    return None

