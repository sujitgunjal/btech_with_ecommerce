import time

from shop_api.services.load import runner
from shop_platform.faults import controller
from tests.conftest import ops_header


def test_load_test_does_not_activate_a_fault(client, ops_on):
    calls = {"count": 0}

    def fake_send(method, path, json=None, headers=None):
        calls["count"] += 1
        return 200

    runner.send = fake_send
    headers = ops_header(client)
    started = client.post(
        "/ops/load",
        headers=headers,
        json={
            "scenario_id": "browse_load",
            "target_service": "ecommerce-shop-api",
            "parameters": {"requests_per_second": 5, "concurrency": 2, "duration_seconds": 5},
        },
    )
    assert started.status_code == 201, started.text
    assert started.json()["kind"] == "load"
    for _ in range(40):
        if calls["count"] >= 1:
            break
        time.sleep(0.05)
    stopped = client.post("/ops/load/stop", headers=headers)
    assert stopped.status_code == 200
    assert stopped.json()["kind"] == "load"
    assert calls["count"] >= 1
    assert controller.snapshot()["active"] is False


def test_fault_and_load_cannot_run_together(client, ops_on):
    headers = ops_header(client)
    fault = client.post(
        "/ops/faults",
        headers=headers,
        json={
            "scenario_id": "slow_search",
            "target_service": "ecommerce-shop-api",
            "parameters": {"delay_ms": 200, "duration_seconds": 30},
        },
    )
    assert fault.status_code == 201
    blocked = client.post(
        "/ops/load",
        headers=headers,
        json={"scenario_id": "search_load", "target_service": "ecommerce-shop-api", "parameters": {}},
    )
    assert blocked.status_code == 409
    client.post("/ops/faults/stop", headers=headers)
