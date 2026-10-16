"""Simulated payment gateway client.

Local mode is used when PAYMENT_SERVICE_URL is empty. HTTP mode calls the
separate payment service and keeps the shop's timeout shorter than a hung gateway.
"""

from __future__ import annotations

import time
import uuid

import httpx

from shop_platform.faults import controller
from shop_platform.settings import get_settings

DECLINE_CARD = "4000000000000002"
TIMEOUT_CARD = "4000000000009995"


class PaymentTimeout(Exception):
    pass


class PaymentFailed(Exception):
    def __init__(self, reason: str, declined: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.declined = declined


def normalize_card(number: str) -> str:
    return "".join(character for character in number if character.isdigit())


def charge(amount_cents: int, card_number: str, idempotency_key: str) -> dict:
    settings = get_settings()
    timeout = controller.dependency_timeout_override() or settings.payment_timeout_seconds
    card = normalize_card(card_number)
    if settings.payment_service_url:
        return _charge_http(settings, amount_cents, card, idempotency_key, timeout)
    return _charge_local(amount_cents, card, idempotency_key, timeout)


def _charge_local(amount_cents: int, card: str, idempotency_key: str, timeout: float) -> dict:
    delay = controller.payment_delay_seconds()
    if card == TIMEOUT_CARD:
        delay = max(delay, timeout + 1)
    if delay > 0:
        time.sleep(min(delay, timeout))
        if delay > timeout:
            raise PaymentTimeout()
    if controller.payment_should_fail():
        raise PaymentFailed("The payment gateway failed the charge")
    if card == DECLINE_CARD:
        raise PaymentFailed("The card was declined", declined=True)
    return {
        "status": "approved",
        "reference": f"local_{idempotency_key[:12]}_{uuid.uuid4().hex[:8]}",
        "amount_cents": amount_cents,
    }


def _charge_http(settings, amount_cents: int, card: str, idempotency_key: str, timeout: float) -> dict:
    try:
        response = httpx.post(
            settings.payment_service_url.rstrip("/") + "/charges",
            json={
                "amount_cents": amount_cents,
                "card_number": card,
                "idempotency_key": idempotency_key,
            },
            headers={"X-Payment-Key": settings.payment_shared_secret},
            timeout=timeout,
        )
    except httpx.TimeoutException as exc:
        raise PaymentTimeout() from exc
    except httpx.HTTPError as exc:
        raise PaymentFailed("The payment gateway could not be reached") from exc
    if response.status_code == 402:
        raise PaymentFailed("The card was declined", declined=True)
    if response.status_code >= 500:
        raise PaymentFailed("The payment gateway failed the charge")
    if response.status_code >= 400:
        raise PaymentFailed("The payment gateway rejected the charge")
    body = response.json()
    if body.get("status") != "approved":
        raise PaymentFailed(body.get("failure_reason") or "The card was declined", declined=True)
    return body
