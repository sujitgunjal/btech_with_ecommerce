"""Services package bridge."""

try:
    from app.services.evidence_service import EvidenceService, get_incident_evidence
except ImportError:
    from backend.app.services.evidence_service import EvidenceService, get_incident_evidence

__all__ = ["EvidenceService", "get_incident_evidence"]
