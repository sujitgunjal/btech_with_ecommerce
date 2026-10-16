import threading

from shop_api.database import SessionLocal
from shop_api.models import CartItem, Product, User
from shop_api.schemas import CheckoutIn
from shop_api.security import hash_password
from shop_api.services.checkout import CheckoutError, place_order
from tests.conftest import auth_header


def _checkout_body():
    return {
        "full_name": "Demo Customer",
        "address_line": "12 Harbour Street",
        "city": "Lisbon",
        "postal_code": "1100-100",
        "country": "Portugal",
        "card": {
            "cardholder_name": "Demo Customer",
            "card_number": "4242424242424242",
            "expiry_month": 12,
            "expiry_year": 2030,
            "cvc": "123",
        },
    }


def test_cart_checkout_and_duplicate_order(client):
    headers = auth_header(client)
    mug = client.get("/products/stoneware-mug").json()
    before = mug["stock"]
    added = client.post("/cart/items", headers=headers, json={"product_id": mug["id"], "quantity": 2})
    assert added.status_code == 201
    assert added.json()["shipping_cents"] == 500
    saved = client.post(f"/wishlist/{mug['id']}", headers=headers)
    assert saved.status_code == 204
    assert len(client.get("/wishlist", headers=headers).json()) == 1

    first = client.post(
        "/checkout",
        headers={**headers, "Idempotency-Key": "order-key-001"},
        json=_checkout_body(),
    )
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["status"] == "processing"
    assert body["payment_status"] == "paid"
    assert body["order_number"].startswith("NL")
    assert body["items"][0]["quantity"] == 2
    assert any(event["status"] == "paid" for event in body["tracking"])

    second = client.post(
        "/checkout",
        headers={**headers, "Idempotency-Key": "order-key-001"},
        json=_checkout_body(),
    )
    assert second.status_code == 200
    assert second.json()["id"] == body["id"]
    assert client.get("/cart", headers=headers).json()["items"] == []

    after = client.get("/products/stoneware-mug").json()["stock"]
    assert after == before - 2
    orders = client.get("/orders", headers=headers)
    assert orders.status_code == 200
    assert orders.json()[0]["order_number"] == body["order_number"]
    detail = client.get(f"/orders/{body['id']}", headers=headers)
    assert detail.status_code == 200


def test_declined_card_restores_stock_and_cart(client):
    headers = auth_header(client)
    mug = client.get("/products/stoneware-mug").json()
    before = mug["stock"]
    client.post("/cart/items", headers=headers, json={"product_id": mug["id"], "quantity": 1})
    body = _checkout_body()
    body["card"]["card_number"] = "4000000000000002"
    response = client.post(
        "/checkout",
        headers={**headers, "Idempotency-Key": "order-key-002"},
        json=body,
    )
    assert response.status_code == 402
    assert client.get("/products/stoneware-mug").json()["stock"] == before
    cart = client.get("/cart", headers=headers).json()
    assert cart["items"][0]["quantity"] == 1
    failed = client.get("/orders", headers=headers).json()[0]
    assert failed["payment_status"] == "declined"


def test_concurrent_checkouts_do_not_oversell(client):
    db = SessionLocal()
    product = db.query(Product).filter(Product.sku == "MUG-04").one()
    product.stock = 3
    db.commit()
    product_id = product.id
    db.close()

    def worker(index):
        session = SessionLocal()
        try:
            user = User(
                email=f"buyer{index}@northline.shop",
                password_hash=hash_password("thread-pass-1"),
                full_name=f"Buyer {index}",
            )
            session.add(user)
            session.commit()
            session.add(CartItem(user_id=user.id, product_id=product_id, quantity=1))
            session.commit()
            body = CheckoutIn(**_checkout_body())
            try:
                order, created = place_order(session, user, body, f"thread-key-{index}")
                return "paid" if created and order.payment_status == "paid" else "other"
            except CheckoutError as exc:
                return exc.status_code
        finally:
            session.close()

    results = []
    threads = [threading.Thread(target=lambda i=i: results.append(worker(i))) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    db = SessionLocal()
    stock = db.get(Product, product_id).stock
    db.close()
    paid = results.count("paid")
    assert stock == 3 - paid
    assert stock >= 0
    assert paid <= 3
    assert paid >= 1
