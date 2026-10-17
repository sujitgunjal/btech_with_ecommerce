"""Publish a fault experiment as an incident the investigation dashboard can list.

The incident description does not include the expected root cause.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import httpx

from shop_platform.settings import get_settings

logger = logging.getLogger("ecommerce.incidents")


def publish_incident(experiment) -> int | None:
    settings = get_settings()
    base = settings.investigation_api_url.rstrip("/")
    if not base:
        return experiment.investigation_incident_id
    if experiment.investigation_incident_id and _incident_exists(base, experiment.investigation_incident_id):
        return experiment.investigation_incident_id
    experiment.investigation_incident_id = None
    duration = 90
    try:
        import json

        duration = int(json.loads(experiment.parameters_json).get("duration_seconds", 90))
    except (TypeError, ValueError):
        duration = 90
    end = experiment.ended_at or (experiment.started_at + timedelta(seconds=duration))
    payload = {
        "title": f"{experiment.scenario_id.replace('_', ' ')} on {experiment.target_service}",
        "description": (
            f"A {experiment.kind} experiment ({experiment.scenario_id}) is active on "
            f"{experiment.target_service}. Investigate telemetry in this window."
        ),
        "service": experiment.target_service,
        "severity": "high" if experiment.kind == "fault" else "medium",
        "start_time": experiment.started_at.isoformat(),
        "end_time": end.isoformat(),
    }
    try:
        response = httpx.post(f"{base}/incidents", json=payload, timeout=5)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Could not record investigation incident: %s", exc)
        return None
    incident_id = response.json().get("id")
    if isinstance(incident_id, int):
        experiment.investigation_incident_id = incident_id
        logger.info(
            "Recorded investigation incident id=%s for experiment id=%s",
            incident_id,
            experiment.id,
        )
        return incident_id
    return None


def _incident_exists(base: str, incident_id: int) -> bool:
    try:
        response = httpx.get(f"{base}/incidents/{incident_id}", timeout=5)
    except httpx.HTTPError as exc:
        logger.warning("Could not check investigation incident %s: %s", incident_id, exc)
        return True
    return response.status_code != 404


def publish_missing_incidents() -> None:
    from shop_api.database import SessionLocal
    from shop_api.models import Experiment

    db = SessionLocal()
    try:
        rows = db.query(Experiment).order_by(Experiment.id.desc()).limit(15).all()
        for row in rows:
            publish_incident(row)
        db.commit()
    finally:
        db.close()


def close_incident(experiment) -> None:
    settings = get_settings()
    base = settings.investigation_api_url.rstrip("/")
    if not base or not experiment.investigation_incident_id or experiment.ended_at is None:
        return
    try:
        httpx.patch(
            f"{base}/incidents/{experiment.investigation_incident_id}",
            json={"end_time": experiment.ended_at.isoformat()},
            timeout=5,
        )
    except httpx.HTTPError as exc:
        logger.warning("Could not close investigation incident: %s", exc)
