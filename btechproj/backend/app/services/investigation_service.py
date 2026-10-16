"""Business logic for investigation orchestration."""

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models.evidence import Evidence
from ..models.incident import Incident
from ..models.investigation import Investigation
from .telemetry_service import TelemetryService

logger = logging.getLogger("incident-backend")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _live_collection_window(
    start_time: datetime,
    end_time: datetime | None,
) -> tuple[datetime, datetime]:
    """Return a window that overlaps telemetry the running stack can contain.

    Scenario files record the original experiment clock. A stack started later
    has logs, metrics, and traces only for the current run, so an old window
    comes back empty.
    """
    now = datetime.now(timezone.utc)
    start_time = _as_utc(start_time)
    end_time = _as_utc(end_time) if end_time is not None else now
    if end_time < now - timedelta(hours=6):
        logger.info(
            "Incident window %s to %s is outside live telemetry; collecting the last 15 minutes",
            start_time.isoformat(),
            end_time.isoformat(),
        )
        return now - timedelta(minutes=15), now
    return start_time, end_time


class InvestigationService:
    """Orchestrates the full investigation workflow.

    Steps 1-8 collect telemetry evidence from Prometheus, Loki, and Jaeger.
    Steps 9-12 run the RAG + LLM investigation pipeline.
    """

    def __init__(self, db: Session):
        self.db = db
        self.telemetry = TelemetryService()

    # ------------------------------------------------------------------
    # Investigation workflow
    # ------------------------------------------------------------------

    async def start_investigation(self, incident: Incident) -> Investigation:
        """Run the full investigation workflow for an incident.

        Steps:
        1. Create Investigation row (pending).
        2. Set incident status -> investigating.
        3. Set investigation status -> collecting.
        4. Determine time window.
        5. Collect telemetry concurrently.
        6. Normalize and store evidence.
        7. Record collector errors as evidence.
        8. Record evidence collection outcome.
        9. Set investigation status -> analyzing.
        10. Retrieve historical incidents via RAG.
        11. Call LLM for root cause analysis.
        12. Store RCA report and set final status.
        """

        # 1. Create investigation
        investigation = Investigation(
            incident_id=incident.id,
            status="pending",
        )
        self.db.add(investigation)
        self.db.commit()
        self.db.refresh(investigation)

        logger.info(
            "Investigation created id=%s incident_id=%s",
            investigation.id,
            incident.id,
        )

        # 2. Update incident status
        incident.status = "investigating"
        self.db.commit()

        # 3. Update investigation status
        investigation.status = "collecting"
        investigation.started_at = datetime.now(timezone.utc)
        self.db.commit()

        # 4. Determine time window
        start_time, end_time = _live_collection_window(
            incident.start_time,
            incident.end_time,
        )
        service_name = incident.service

        # 5. Collect telemetry
        logger.info(
            "Collecting telemetry service=%s start=%s end=%s",
            service_name,
            start_time,
            end_time,
        )

        events, errors = await self.telemetry.collect_all(
            service=service_name,
            start_time=start_time,
            end_time=end_time,
        )

        # 6. Store evidence
        evidence_count = 0
        for event in events:
            evidence_row = Evidence(
                incident_id=incident.id,
                source=event.source,
                service=event.service,
                timestamp=event.timestamp,
                event_type=event.event_type,
                severity=event.severity,
                content=event.content,
                metadata_=event.metadata,
            )
            self.db.add(evidence_row)
            evidence_count += 1

        self.db.commit()
        logger.info("Evidence stored count=%d", evidence_count)

        # 7. Store collector errors as evidence
        for error in errors:
            error_evidence = Evidence(
                incident_id=incident.id,
                source=error["source"],
                service=error.get("service", service_name),
                timestamp=datetime.now(timezone.utc),
                event_type="collector_error",
                severity="warning",
                content=error["message"],
                metadata_={"error_type": error["error_type"]},
            )
            self.db.add(error_evidence)

        self.db.commit()

        # 8. Record evidence collection outcome
        total_collectors = self.telemetry.collector_count(service_name)
        failed_collectors = len(errors)

        if failed_collectors == total_collectors:
            collection_status = "failed"
        elif failed_collectors > 0:
            collection_status = "partial"
        else:
            collection_status = "complete"

        logger.info(
            "Evidence collection %s: evidence=%d errors=%d",
            collection_status,
            evidence_count,
            failed_collectors,
        )

        # ---------------------------------------------------------------
        # 9-12. RAG + LLM analysis
        # ---------------------------------------------------------------
        investigation.status = "analyzing"
        self.db.commit()

        rca_result = await self._run_analysis(incident)

        if rca_result is not None:
            investigation.report = json.dumps(rca_result, default=str)
            investigation.confidence = rca_result.get("confidence")
            if collection_status == "complete":
                investigation.status = "completed"
            else:
                investigation.status = "completed_partial"
        elif evidence_count > 0:
            investigation.status = "completed_partial"
        else:
            investigation.status = "failed"

        investigation.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(investigation)

        logger.info(
            "Investigation %s id=%s evidence=%d confidence=%s",
            investigation.status,
            investigation.id,
            evidence_count,
            investigation.confidence,
        )

        return investigation

    async def _run_analysis(self, incident: Incident) -> dict | None:
        """Run the RAG + LLM analysis pipeline.

        Returns the RCA dict on success, or None on failure.
        """
        try:
            from ..investigation.engine import InvestigationEngine

            evidence_rows = (
                self.db.query(Evidence)
                .filter(
                    Evidence.incident_id == incident.id,
                    Evidence.event_type != "collector_error",
                )
                .order_by(Evidence.timestamp.asc())
                .all()
            )

            engine = InvestigationEngine()
            rca = await engine.investigate(incident, evidence_rows)
            return rca

        except Exception as exc:
            logger.error(
                "Analysis pipeline failed for incident_id=%s: %s",
                incident.id,
                exc,
                exc_info=True,
            )
            return None

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, investigation_id: int) -> Investigation | None:
        """Get a single investigation by ID."""
        return (
            self.db.query(Investigation)
            .filter(Investigation.id == investigation_id)
            .first()
        )

    def count_evidence(self, incident_id: int) -> int:
        """Count evidence rows for an incident."""
        return (
            self.db.query(Evidence)
            .filter(Evidence.incident_id == incident_id)
            .count()
        )

    def get_evidence_for_investigation(
        self, investigation_id: int
    ) -> list[Evidence] | None:
        """Get evidence associated with an investigation's incident."""
        investigation = self.get(investigation_id)
        if investigation is None:
            return None
        return (
            self.db.query(Evidence)
            .filter(Evidence.incident_id == investigation.incident_id)
            .order_by(Evidence.timestamp.asc())
            .all()
        )
