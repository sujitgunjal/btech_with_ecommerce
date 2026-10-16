"""Bounded load generator.

The runner calls the shop's real HTTP API. It does not set fault flags.
Request rate, concurrency, and duration are the validated catalogue values.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import httpx

from shop_platform.settings import get_settings

logger = logging.getLogger("ecommerce.load")


class LoadRunner:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.scenario_id: str | None = None
        self.stats = {"requests": 0, "errors": 0}
        self._lock = threading.Lock()
        self.send: Callable[..., int] | None = None

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, scenario_id: str, params: dict, on_finished: Callable[[dict, str], None]) -> None:
        if self.running():
            raise RuntimeError("A load test is already running")
        self._stop.clear()
        self.scenario_id = scenario_id
        self.stats = {"requests": 0, "errors": 0}
        self._thread = threading.Thread(
            target=self._run,
            args=(scenario_id, params, on_finished),
            name="ecommerce-load",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.scenario_id = None

    def _run(self, scenario_id: str, params: dict, on_finished: Callable[[dict, str], None]) -> None:
        deadline = time.time() + int(params["duration_seconds"])
        interval = 1 / max(int(params["requests_per_second"]), 1)
        workers = int(params["concurrency"])
        token: dict[str, str] = {}
        reason = "completed"
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = []
            while time.time() < deadline and not self._stop.is_set():
                futures.append(pool.submit(self._dispatch, scenario_id, token))
                time.sleep(interval)
            if self._stop.is_set():
                reason = "stopped"
            for future in futures:
                try:
                    future.result(timeout=8)
                except Exception:
                    self._mark(error=True)
        self.scenario_id = None
        logger.info(
            "background traffic run finished requests=%s errors=%s",
            self.stats["requests"],
            self.stats["errors"],
        )
        on_finished(dict(self.stats), reason)

    def _dispatch(self, scenario_id: str, token: dict) -> None:
        try:
            if scenario_id == "browse_load":
                self._request("GET", "/categories")
                self._request("GET", "/products?limit=12")
            elif scenario_id == "search_load":
                self._request("GET", "/products?q=linen")
            elif scenario_id == "checkout_load":
                self._checkout_once(token)
            else:
                choice = self.stats["requests"] % 3
                if choice == 0:
                    self._request("GET", "/products?limit=12")
                elif choice == 1:
                    self._request("GET", "/products?q=wool")
                else:
                    self._checkout_once(token)
        except Exception:
            self._mark(error=True)

    def _checkout_once(self, token: dict) -> None:
        if "access_token" not in token:
            settings = get_settings()
            status, body = self._request(
                "POST",
                "/auth/login",
                json={"email": settings.load_test_email, "password": settings.load_test_password},
                counted=False,
            )
            if status != 200 or not isinstance(body, dict):
                self._mark(error=True)
                return
            token["access_token"] = body["access_token"]
            token["user"] = body
        headers = {"Authorization": f"Bearer {token['access_token']}"}
        status, page = self._request("GET", "/products?q=studio%20tote", counted=False)
        if status != 200 or not page.get("items"):
            self._mark(error=True)
            return
        product_id = page["items"][0]["id"]
        self._request(
            "POST",
            "/cart/items",
            json={"product_id": product_id, "quantity": 1},
            headers=headers,
        )
        profile_status, profile = self._request("GET", "/auth/me", headers=headers, counted=False)
        if profile_status != 200:
            self._mark(error=True)
            return
        self._request(
            "POST",
            "/checkout",
            headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
            json={
                "full_name": profile["full_name"],
                "address_line": profile["address_line"],
                "city": profile["city"],
                "postal_code": profile["postal_code"],
                "country": profile["country"],
                "card": {
                    "cardholder_name": profile["full_name"],
                    "card_number": "4242424242424242",
                    "expiry_month": 12,
                    "expiry_year": 2030,
                    "cvc": "123",
                },
            },
        )

    def _request(self, method: str, path: str, json: dict | None = None, headers: dict | None = None, counted: bool = True):
        status = 0
        body = None
        try:
            if self.send is not None:
                status = self.send(method, path, json=json, headers=headers)
            else:
                settings = get_settings()
                response = httpx.request(
                    method,
                    settings.internal_base_url.rstrip("/") + path,
                    json=json,
                    headers=headers,
                    timeout=8,
                )
                status = response.status_code
                if response.headers.get("content-type", "").startswith("application/json"):
                    body = response.json()
        except Exception:
            status = 0
        if counted:
            self._mark(error=status < 200 or status >= 400)
        return status, body

    def _mark(self, error: bool) -> None:
        with self._lock:
            self.stats["requests"] += 1
            if error:
                self.stats["errors"] += 1


runner = LoadRunner()
