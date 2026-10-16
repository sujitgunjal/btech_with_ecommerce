import time

from shop_platform.settings import get_settings
from tests.conftest import auth_header


def test_slow_card_times_out_and_restores_stock(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "payment_timeout_seconds", 0.2)
    headers = auth_header(client)
    mug = client.get("/products/stoneware-mug").json()
    before = mug["stock"]
    client.post("/cart/items", headers=headers, json={"product_id": mug["id"], "quantity": 1})
    body = {
        "full_name": "Demo Customer",
        "address_line": "12 Harbour Street",
        "city": "Lisbon",
        "postal_code": "1100-100",
        "country": "Portugal",
        "card": {
            "cardholder_name": "Demo Customer",
            "card_number": "4000000000009995",
            "expiry_month": 12,
            "expiry_year": 2030,
            "cvc": "123",
        },
    }
    started = time.perf_counter()
    response = client.post(
        "/checkout",
        headers={**headers, "Idempotency-Key": "timeout-key-01"},
        json=body,
    )
    elapsed = time.perf_counter() - started
    assert response.status_code == 504
    assert elapsed < 2
    assert client.get("/products/stoneware-mug").json()["stock"] == before
    assert client.get("/orders", headers=headers).json()[0]["payment_status"] == "timeout"
