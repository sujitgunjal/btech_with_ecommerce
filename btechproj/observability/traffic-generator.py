import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:8000")
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8000")
ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order-service:8000")


def request(method, url, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    started = time.monotonic()
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, data=data, headers=headers, method=method),
            timeout=7,
        ) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as error:
        elapsed_ms = (time.monotonic() - started) * 1000
        print(
            f"{datetime.now(timezone.utc).isoformat()} "
            f"request returned HTTP {error.code}: {method} {url} "
            f"duration_ms={elapsed_ms:.1f}",
            flush=True,
        )
        return error.code, None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        elapsed_ms = (time.monotonic() - started) * 1000
        print(
            f"{datetime.now(timezone.utc).isoformat()} "
            f"request failed: {method} {url}: {error} "
            f"duration_ms={elapsed_ms:.1f}",
            flush=True,
        )
        return None, None


def ensure_data():
    status, users = request("GET", f"{USER_SERVICE_URL}/users")
    if status != 200:
        return None, None
    if not users:
        _, user = request(
            "POST",
            f"{USER_SERVICE_URL}/users",
            {"name": "Traffic Generator User", "email": "traffic@example.com"},
        )
    else:
        user = users[0]

    status, products = request("GET", f"{PRODUCT_SERVICE_URL}/products")
    if status != 200:
        return None, None
    if not products:
        _, product = request(
            "POST",
            f"{PRODUCT_SERVICE_URL}/products",
            {
                "name": "Traffic Generator Product",
                "description": "Synthetic traffic fixture",
                "price": 10.0,
                "stock": 10000,
            },
        )
    else:
        product = next((item for item in products if item["stock"] > 0), products[0])
    return user, product


user = None
product = None

while True:
    if not user or not product:
        user, product = ensure_data()
    if user and product:
        status, order = request(
            "POST",
            f"{ORDER_SERVICE_URL}/orders",
            {"user_id": user["id"], "product_id": product["id"], "quantity": 1},
        )
        if status == 201 and order:
            request("GET", f"{ORDER_SERVICE_URL}/orders/{order['id']}")
        request("GET", f"{USER_SERVICE_URL}/users/{user['id']}")
        request("GET", f"{PRODUCT_SERVICE_URL}/products/{product['id']}")
    time.sleep(2)
