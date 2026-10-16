"""Development-only experiment control.

Every route returns 404 unless the process is explicitly in development or
testing and FAULT_INJECTION_ENABLED is true. Parameters come only from the
catalogue. Expected root causes are stored on the experiment row and are not
written to application logs.
"""

from __future__ import annotations

import hmac
import json
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from shop_api.database import SessionLocal, engine
from shop_api.deps import require_ops
from shop_api.models import Experiment, utcnow
from shop_api.schemas import ExperimentOut, ExperimentStartIn, OpsLoginIn, TokenOut
from shop_api.security import create_ops_token
from shop_api.services.load import runner
from shop_platform.catalogue import CatalogueError, load_catalogue, scenarios_by_kind, validate_selection
from shop_platform.faults import controller
from shop_platform.settings import get_settings

def gate() -> None:
    require_enabled()


router = APIRouter(prefix="/ops", dependencies=[Depends(gate)])


def ops_available() -> bool:
    settings = get_settings()
    return (
        settings.app_env in {"development", "testing"}
        and settings.fault_injection_enabled
        and len(settings.ops_username) >= 3
        and len(settings.ops_password) >= 5
    )


def require_enabled() -> None:
    if not ops_available():
        raise HTTPException(status_code=404, detail="Not found")


def _finish_running(outcome: str, detail: str = "") -> None:
    db = SessionLocal()
    try:
        row = (
            db.query(Experiment)
            .filter(Experiment.outcome == "running")
            .order_by(Experiment.id.desc())
            .first()
        )
        if row is not None:
            row.outcome = outcome
            row.ended_at = datetime.now(timezone.utc)
            row.detail = detail[:500]
            from shop_api.services.investigation_bridge import close_incident

            close_incident(row)
            db.commit()
    finally:
        db.close()


def recover_orphan_experiments() -> None:
    db = SessionLocal()
    try:
        rows = db.query(Experiment).filter(Experiment.outcome == "running").all()
        for row in rows:
            row.outcome = "expired"
            row.ended_at = utcnow()
            row.detail = "The process restarted before the experiment finished"
        if rows:
            db.commit()
    finally:
        db.close()


def _experiment_out(row: Experiment) -> ExperimentOut:
    return ExperimentOut(
        id=row.id,
        kind=row.kind,  # type: ignore[arg-type]
        scenario_id=row.scenario_id,
        target_service=row.target_service,
        parameters=json.loads(row.parameters_json),
        expected_root_cause=row.expected_root_cause,
        outcome=row.outcome,
        detail=row.detail,
        started_at=row.started_at,
        ended_at=row.ended_at,
    )


def _running(db: Session) -> Experiment | None:
    return db.query(Experiment).filter(Experiment.outcome == "running").one_or_none()


def _payment_call(path: str, payload: dict | None = None) -> None:
    settings = get_settings()
    if not settings.payment_service_url:
        return
    if not settings.internal_fault_token:
        raise HTTPException(status_code=503, detail="Payment fault control is not configured")
    try:
        response = httpx.post(
            settings.payment_service_url.rstrip("/") + path,
            json=payload or {},
            headers={"X-Fault-Token": settings.internal_fault_token},
            timeout=3,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="The payment gateway could not apply the experiment") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=503, detail="The payment gateway refused the experiment")


def _clear_payment() -> None:
    settings = get_settings()
    if not settings.payment_service_url or not settings.internal_fault_token:
        return
    try:
        httpx.post(
            settings.payment_service_url.rstrip("/") + "/internal/faults/clear",
            headers={"X-Fault-Token": settings.internal_fault_token},
            timeout=3,
        )
    except httpx.HTTPError:
        return


@router.post("/login", response_model=TokenOut)
def login(body: OpsLoginIn):
    require_enabled()
    settings = get_settings()
    username_ok = hmac.compare_digest(body.username, settings.ops_username)
    password_ok = hmac.compare_digest(body.password, settings.ops_password)
    if not (username_ok and password_ok):
        raise HTTPException(status_code=401, detail="Operator credentials were rejected")
    return TokenOut(access_token=create_ops_token(settings.ops_username))


@router.get("/scenarios")
def scenarios(_: str = Depends(require_ops)):
    require_enabled()
    return load_catalogue()


@router.get("/status")
def status(_: str = Depends(require_ops)):
    require_enabled()
    return _status_payload()


def _payment_fault_snapshot() -> dict:
    settings = get_settings()
    if not settings.payment_service_url or not settings.internal_fault_token:
        return {"active": False, "scenario_id": None, "parameters": {}}
    try:
        response = httpx.get(
            settings.payment_service_url.rstrip("/") + "/internal/faults",
            headers={"X-Fault-Token": settings.internal_fault_token},
            timeout=2,
        )
        if response.status_code == 200:
            return response.json()
    except httpx.HTTPError:
        return {"active": False, "scenario_id": None, "parameters": {}, "reachable": False}
    return {"active": False, "scenario_id": None, "parameters": {}}


def _status_payload() -> dict:
    db = SessionLocal()
    try:
        current = _running(db)
        shop_fault = controller.snapshot()
        payment_fault = _payment_fault_snapshot()
        return {
            "fault": shop_fault if shop_fault["active"] else payment_fault,
            "shop_fault": shop_fault,
            "payment_fault": payment_fault,
            "load": {"active": runner.running(), "scenario_id": runner.scenario_id, "stats": dict(runner.stats)},
            "experiment": None if current is None else _experiment_out(current).model_dump(mode="json"),
        }
    finally:
        db.close()


@router.get("/experiments", response_model=list[ExperimentOut])
def experiments(_: str = Depends(require_ops)):
    require_enabled()
    db = SessionLocal()
    try:
        rows = db.query(Experiment).order_by(Experiment.id.desc()).limit(50).all()
        return [_experiment_out(row) for row in rows]
    finally:
        db.close()


@router.post("/faults", response_model=ExperimentOut, status_code=201)
def start_fault(body: ExperimentStartIn, _: str = Depends(require_ops)):
    require_enabled()
    return _start("fault", body)


@router.post("/faults/stop", response_model=ExperimentOut)
def stop_fault(_: str = Depends(require_ops)):
    require_enabled()
    db = SessionLocal()
    try:
        row = _running(db)
        if row is None or row.kind != "fault":
            raise HTTPException(status_code=404, detail="No fault experiment to stop")
    finally:
        db.close()
    controller.clear("stopped")
    _clear_payment()
    _finish_running("stopped", "Stopped by the operator")
    db = SessionLocal()
    try:
        row = db.query(Experiment).order_by(Experiment.id.desc()).first()
        return _experiment_out(row)
    finally:
        db.close()


@router.post("/load", response_model=ExperimentOut, status_code=201)
def start_load(body: ExperimentStartIn, _: str = Depends(require_ops)):
    require_enabled()
    return _start("load", body)


@router.post("/load/stop", response_model=ExperimentOut)
def stop_load(_: str = Depends(require_ops)):
    require_enabled()
    db = SessionLocal()
    try:
        row = _running(db)
        if row is None or row.kind != "load":
            raise HTTPException(status_code=404, detail="No load experiment to stop")
    finally:
        db.close()
    runner.stop()
    db = SessionLocal()
    try:
        row = db.query(Experiment).order_by(Experiment.id.desc()).first()
        return _experiment_out(row)
    finally:
        db.close()


def _start(kind: str, body: ExperimentStartIn) -> ExperimentOut:
    try:
        params = validate_selection(body.scenario_id, kind, body.target_service, body.parameters)
        scenario = next(item for item in scenarios_by_kind(kind) if item["id"] == body.scenario_id)
    except CatalogueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except StopIteration as exc:
        raise HTTPException(status_code=422, detail="Unknown scenario") from exc

    db = SessionLocal()
    try:
        if _running(db) is not None or controller.snapshot()["active"] or runner.running():
            raise HTTPException(status_code=409, detail="An experiment is already running")
        row = Experiment(
            kind=kind,
            scenario_id=scenario["id"],
            target_service=body.target_service,
            parameters_json=json.dumps(params),
            expected_root_cause=scenario["expected_root_cause"],
            outcome="running",
            detail="",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        payload = _experiment_out(row)
    finally:
        db.close()

    try:
        if kind == "fault":
            _activate_fault(scenario["id"], body.target_service, params)
        else:
            runner.start(scenario["id"], params, _load_finished)
    except HTTPException:
        _finish_running("failed", "The experiment could not be applied")
        controller.clear("stopped")
        _clear_payment()
        raise
    except Exception as exc:
        _finish_running("failed", "The experiment could not be applied")
        controller.clear("stopped")
        _clear_payment()
        raise HTTPException(status_code=503, detail="The experiment could not be applied") from exc
    _remember_incident(payload.id)
    return payload


def _remember_incident(experiment_id: int) -> None:
    from shop_api.services.investigation_bridge import publish_incident

    db = SessionLocal()
    try:
        row = db.get(Experiment, experiment_id)
        if row is not None:
            publish_incident(row)
            db.commit()
    finally:
        db.close()


def _activate_fault(scenario_id: str, target: str, params: dict) -> None:
    settings = get_settings()
    if scenario_id == "dependency_timeout":
        controller.apply(scenario_id, params, engine if _needs_engine(scenario_id) else None)
        if settings.payment_service_url:
            _payment_call("/internal/faults/apply", {"scenario_id": scenario_id, "parameters": params})
        return
    if target == "ecommerce-payment-gateway":
        if settings.payment_service_url:
            _payment_call("/internal/faults/apply", {"scenario_id": scenario_id, "parameters": params})
        else:
            controller.apply(scenario_id, params, None)
        return
    controller.apply(scenario_id, params, engine if _needs_engine(scenario_id) else None)


def _needs_engine(scenario_id: str) -> bool:
    return scenario_id == "db_pool_exhaustion"


def _load_finished(stats: dict, reason: str) -> None:
    _finish_running(reason, f"requests={stats['requests']} errors={stats['errors']}")


controller.on_expired = lambda: _finish_running("expired", "The duration elapsed")
