from fastapi.testclient import TestClient

from payment_service.main import DECLINE_CARD, app as payment_app
from shop_platform.faults import controller
from shop_platform.settings import get_settings


def test_payment_approves_declines_and_hides_fault_routes():
    settings = get_settings()
    controller.clear("stopped")
    with TestClient(payment_app) as client:
        denied = client.post(
            "/charges",
            json={"amount_cents": 1000, "card_number": "4242424242424242", "idempotency_key": "pay-key-0001"},
        )
        assert denied.status_code == 401
        approved = client.post(
            "/charges",
            headers={"X-Payment-Key": settings.payment_shared_secret},
            json={"amount_cents": 1000, "card_number": "4242424242424242", "idempotency_key": "pay-key-0001"},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"
        again = client.post(
            "/charges",
            headers={"X-Payment-Key": settings.payment_shared_secret},
            json={"amount_cents": 1000, "card_number": "4242424242424242", "idempotency_key": "pay-key-0001"},
        )
        assert again.json()["reference"] == approved.json()["reference"]
        declined = client.post(
            "/charges",
            headers={"X-Payment-Key": settings.payment_shared_secret},
            json={"amount_cents": 1000, "card_number": DECLINE_CARD, "idempotency_key": "pay-key-0002"},
        )
        assert declined.status_code == 402
        hidden = client.post(
            "/internal/faults/apply",
            json={"scenario_id": "cpu_high", "parameters": {"workers": 1, "duration_seconds": 10}},
        )
        assert hidden.status_code == 404
    controller.clear("stopped")
