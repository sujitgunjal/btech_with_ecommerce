"""Health-check endpoints (liveness and readiness)."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db

logger = logging.getLogger("incident-backend")

router = APIRouter()


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Combined health check — verifies the service and its database."""
    checks: dict[str, bool] = {"database": False}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as exc:
        logger.warning("Database health check failed: %s", exc)

    overall = all(checks.values())
    return {
        "status": "healthy" if overall else "unhealthy",
        "service": "incident-backend",
        "checks": checks,
    }


@router.get("/health/live")
def liveness():
    """Liveness probe — the application process is running."""
    return {
        "status": "healthy",
        "service": "incident-backend",
    }


@router.get("/health/ready")
def readiness(db: Session = Depends(get_db)):
    """Readiness probe — dependencies (DB) are reachable."""
    checks: dict[str, bool] = {"database": False}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as exc:
        logger.warning("Database readiness check failed: %s", exc)

    overall = all(checks.values())
    return {
        "status": "ready" if overall else "not_ready",
        "service": "incident-backend",
        "checks": checks,
    }
