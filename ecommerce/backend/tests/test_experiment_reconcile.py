from datetime import datetime, timedelta, timezone

from shop_api.database import SessionLocal
from shop_api.models import Experiment
from shop_api.services.investigation_bridge import publish_incident
from shop_platform.faults import controller
from tests.conftest import ops_header


def test_elapsed_experiment_no_longer_blocks_the_next_one(client, ops_on):
    db = SessionLocal()
    try:
        stale = Experiment(
            kind="fault",
            scenario_id="memory_pressure",
            target_service="ecommerce-payment-gateway",
            parameters_json='{"memory_mb": 16, "duration_seconds": 30}',
            expected_root_cause="stored only",
            outcome="running",
            detail="",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        db.add(stale)
        db.commit()
    finally:
        db.close()

    headers = ops_header(client)
    status = client.get("/ops/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["experiment"] is None
    assert status.json()["fault"]["active"] is False

    started = client.post(
        "/ops/faults",
        headers=headers,
        json={
            "scenario_id": "elevated_5xx",
            "target_service": "ecommerce-shop-api",
            "parameters": {"error_percent": 100, "duration_seconds": 30},
        },
    )
    assert started.status_code == 201, started.text
    client.post("/ops/faults/stop", headers=headers)
    controller.clear("stopped")


def test_deleted_investigation_incident_is_recorded_again(monkeypatch):
    calls = {"get": 0, "post": 0}

    class Response:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self._payload = payload or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError("failed")

        def json(self):
            return self._payload

    def fake_get(url, timeout=5):
        calls["get"] += 1
        return Response(404)

    def fake_post(url, json=None, timeout=5):
        calls["post"] += 1
        return Response(201, {"id": 90})

    monkeypatch.setattr("shop_api.services.investigation_bridge.httpx.get", fake_get)
    monkeypatch.setattr("shop_api.services.investigation_bridge.httpx.post", fake_post)
    monkeypatch.setattr(
        "shop_api.services.investigation_bridge.get_settings",
        lambda: type("S", (), {"investigation_api_url": "http://investigation.example"})(),
    )

    class Row:
        investigation_incident_id = 53
        started_at = datetime.now(timezone.utc)
        ended_at = None
        parameters_json = '{"duration_seconds": 45}'
        scenario_id = "memory_pressure"
        target_service = "ecommerce-payment-gateway"
        kind = "fault"
        id = 14

    row = Row()
    assert publish_incident(row) == 90
    assert calls["get"] == 1
    assert calls["post"] == 1
    assert row.investigation_incident_id == 90
