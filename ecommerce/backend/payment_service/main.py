"""Simulated card gateway.

The shop API is the only caller. Fault routes accept a shared token and the
same environment safeguard as the shop. They never accept shell commands.
"""

from __future__ import annotations

import hmac
import logging
import threading
import time
import uuid

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from shop_platform.faults import controller
from shop_platform.gate import FaultGate
from shop_platform.logging_json import configure_logging
from shop_platform.settings import get_settings
from shop_platform.telemetry import init_telemetry

settings = get_settings()
configure_logging(settings.otel_service_name)
logger = logging.getLogger("ecommerce.payment")

app = FastAPI(title="Northline Payment Gateway", version="1.0.0")
app.add_middleware(FaultGate)
init_telemetry(
    app,
    None,
    settings.otel_service_name,
    settings.otel_exporter_otlp_endpoint,
    settings.deployment_environment,
)

_results: dict[str, dict] = {}
_lock = threading.Lock()
DECLINE_CARD = "4000000000000002"
TIMEOUT_CARD = "4000000000009995"


class ChargeIn(BaseModel):
    amount_cents: int = Field(gt=0, le=5_000_000)
    card_number: str = Field(min_length=13, max_length=19)
    idempotency_key: str = Field(min_length=8, max_length=80)


class FaultIn(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=64)
    parameters: dict[str, int]


def _same(left: str | None, right: str) -> bool:
    if left is None or not right or len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def _require_payment_key(payment_key: str | None) -> None:
    if not _same(payment_key, settings.payment_shared_secret):
        raise HTTPException(status_code=401, detail="Payment key rejected")


def _require_fault_token(fault_token: str | None) -> None:
    allowed = (
        settings.app_env in {"development", "testing"}
        and settings.fault_injection_enabled
        and _same(fault_token, settings.internal_fault_token)
    )
    if not allowed:
        raise HTTPException(status_code=404, detail="Not found")


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.otel_service_name}


@app.get("/internal/faults")
def fault_status(x_fault_token: str | None = Header(default=None)):
    _require_fault_token(x_fault_token)
    return controller.snapshot()


@app.post("/charges")
def charge(body: ChargeIn, x_payment_key: str | None = Header(default=None)):
    _require_payment_key(x_payment_key)
    with _lock:
        cached = _results.get(body.idempotency_key)
    if cached is not None:
        return cached

    delay = controller.payment_delay_seconds()
    if body.card_number == TIMEOUT_CARD:
        delay = max(delay, settings.payment_timeout_seconds + 1)
    if delay:
        time.sleep(delay)

    if controller.payment_should_fail():
        logger.error("payment gateway failed a charge amount_cents=%s", body.amount_cents)
        raise HTTPException(status_code=502, detail="The payment gateway failed the charge")
    if body.card_number == DECLINE_CARD:
        logger.info("payment declined amount_cents=%s", body.amount_cents)
        raise HTTPException(status_code=402, detail="The card was declined")

    result = {
        "status": "approved",
        "reference": f"pay_{uuid.uuid4().hex[:12]}",
        "amount_cents": body.amount_cents,
    }
    with _lock:
        _results[body.idempotency_key] = result
    logger.info("payment approved amount_cents=%s", body.amount_cents)
    return result


@app.post("/internal/faults/apply")
def apply_fault(body: FaultIn, x_fault_token: str | None = Header(default=None)):
    _require_fault_token(x_fault_token)
    allowed = {
        "cpu_high",
        "memory_pressure",
        "slow_responses",
        "elevated_5xx",
        "payment_timeout",
        "payment_failure",
        "service_unavailable",
        "dependency_timeout",
    }
    if body.scenario_id not in allowed:
        raise HTTPException(status_code=422, detail="This scenario cannot run on the payment gateway")
    duration = int(body.parameters.get("duration_seconds", 30))
    if duration < 5 or duration > 120:
        raise HTTPException(status_code=422, detail="Duration is outside the allowed range")
    controller.apply(body.scenario_id, body.parameters, None)
    return {"active": True}


@app.post("/internal/faults/clear")
def clear_fault(x_fault_token: str | None = Header(default=None)):
    _require_fault_token(x_fault_token)
    controller.clear("stopped")
    return {"active": False}
