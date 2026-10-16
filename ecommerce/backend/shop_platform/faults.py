"""In-process fault controls.

This module can only apply catalogue scenarios that were already validated.
It has no shell, no Docker client, and no arbitrary code path.
"""

from __future__ import annotations

import random
import threading
import time
from typing import Callable


class FaultController:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.scenario_id: str | None = None
        self.params: dict = {}
        self.expires_at: float = 0.0
        self._timer: threading.Timer | None = None
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._memory: bytearray | None = None
        self._connections: list = []
        self.on_expired: Callable[[], None] | None = None

    def snapshot(self) -> dict:
        with self._lock:
            if self.scenario_id and time.time() >= self.expires_at:
                scenario = self.scenario_id
                self._release_unlocked()
                self.scenario_id = None
                self.params = {}
                expired = scenario
            else:
                expired = None
            current = {
                "active": self.scenario_id is not None,
                "scenario_id": self.scenario_id,
                "parameters": dict(self.params),
                "expires_at": self.expires_at if self.scenario_id else None,
            }
        if expired and self.on_expired:
            self.on_expired()
        return current

    def apply(self, scenario_id: str, params: dict, engine=None) -> None:
        duration = int(params.get("duration_seconds", 30))
        with self._lock:
            self._release_unlocked()
            self._stop.clear()
            self.scenario_id = scenario_id
            self.params = dict(params)
            self.expires_at = time.time() + duration
            self._start_resources(scenario_id, params, engine)
            if self._timer:
                self._timer.cancel()
            timer = threading.Timer(duration, self.clear, kwargs={"reason": "expired"})
            timer.daemon = True
            self._timer = timer
            timer.start()

    def clear(self, reason: str = "stopped") -> None:
        should_notify = False
        with self._lock:
            if self.scenario_id is None and not self._connections and self._memory is None:
                if self._timer:
                    self._timer.cancel()
                    self._timer = None
                return
            self._release_unlocked()
            self.scenario_id = None
            self.params = {}
            self.expires_at = 0.0
            if self._timer:
                self._timer.cancel()
                self._timer = None
            should_notify = reason == "expired"
        if should_notify and self.on_expired:
            self.on_expired()

    def _start_resources(self, scenario_id: str, params: dict, engine) -> None:
        if scenario_id == "cpu_high":
            workers = int(params.get("workers", 1))
            for _ in range(workers):
                thread = threading.Thread(target=self._burn, name="ecommerce-cpu", daemon=True)
                self._threads.append(thread)
                thread.start()
        elif scenario_id == "memory_pressure":
            size = int(params.get("memory_mb", 16)) * 1024 * 1024
            block = bytearray(size)
            for index in range(0, size, 4096):
                block[index] = 1
            self._memory = block
        elif scenario_id == "db_pool_exhaustion" and engine is not None:
            count = int(params.get("connections", 1))
            for _ in range(count):
                self._connections.append(engine.connect())

    def _release_unlocked(self) -> None:
        self._stop.set()
        threads = list(self._threads)
        self._threads = []
        for thread in threads:
            thread.join(timeout=1)
        self._memory = None
        connections = list(self._connections)
        self._connections = []
        for connection in connections:
            connection.close()

    def _burn(self) -> None:
        while not self._stop.is_set():
            value = 0
            for index in range(20000):
                value += index * index
            if value == -1:
                break

    def response_delay_seconds(self, path: str, query: str) -> float:
        current = self.snapshot()
        if not current["active"]:
            return 0.0
        scenario = current["scenario_id"]
        params = current["parameters"]
        if scenario == "slow_responses":
            return params.get("delay_ms", 0) / 1000
        if scenario == "slow_search" and path.startswith("/products") and "q=" in query and "q=&" not in f"{query}&":
            if _query_has_value(query, "q"):
                return params.get("delay_ms", 0) / 1000
        return 0.0

    def forced_status(self, path: str) -> int | None:
        current = self.snapshot()
        if not current["active"]:
            return None
        scenario = current["scenario_id"]
        if scenario == "service_unavailable":
            return 503
        if scenario == "elevated_5xx":
            percent = current["parameters"].get("error_percent", 0)
            if random.randint(1, 100) <= percent:
                return 500
        return None

    def checkout_delay_seconds(self) -> float:
        current = self.snapshot()
        if current["active"] and current["scenario_id"] == "slow_checkout":
            return current["parameters"].get("delay_ms", 0) / 1000
        return 0.0

    def inventory_conflict_active(self) -> bool:
        current = self.snapshot()
        return bool(current["active"] and current["scenario_id"] == "inventory_conflict")

    def database_delay_seconds(self) -> float:
        current = self.snapshot()
        if current["active"] and current["scenario_id"] == "db_latency":
            return current["parameters"].get("delay_ms", 0) / 1000
        return 0.0

    def payment_delay_seconds(self) -> float:
        current = self.snapshot()
        if not current["active"]:
            return 0.0
        if current["scenario_id"] in {"payment_timeout", "dependency_timeout"}:
            return current["parameters"].get("delay_ms", 0) / 1000
        return 0.0

    def payment_should_fail(self) -> bool:
        current = self.snapshot()
        if not (current["active"] and current["scenario_id"] == "payment_failure"):
            return False
        return random.randint(1, 100) <= current["parameters"].get("error_percent", 100)

    def dependency_timeout_override(self) -> float | None:
        current = self.snapshot()
        if current["active"] and current["scenario_id"] == "dependency_timeout":
            return 0.4
        return None


def _query_has_value(query: str, key: str) -> bool:
    for part in query.split("&"):
        name, _, value = part.partition("=")
        if name == key and value.strip():
            return True
    return False


controller = FaultController()
