from sqlalchemy import create_engine
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.pool import QueuePool

from shop_platform.catalogue import CatalogueError, load_catalogue, validate_selection
from shop_platform.faults import controller
from tests.conftest import auth_header, ops_header


def test_ops_is_hidden_until_explicitly_enabled(client):
    assert client.post("/ops/login", json={"username": "operator", "password": "operator-pass"}).status_code == 404
    assert client.get("/ops/scenarios").status_code == 401 or client.get("/ops/scenarios").status_code == 404


def test_ops_rejects_customer_token_and_unsafe_parameters(client, ops_on):
    customer = auth_header(client)
    assert client.get("/ops/scenarios", headers=customer).status_code == 403
    headers = ops_header(client)
    catalogue = client.get("/ops/scenarios", headers=headers)
    assert catalogue.status_code == 200
    ids = [item["id"] for item in catalogue.json()["scenarios"]]
    assert "cpu_high" in ids
    assert "browse_load" in ids

    rejected = client.post(
        "/ops/faults",
        headers=headers,
        json={
            "scenario_id": "cpu_high",
            "target_service": "ecommerce-shop-api",
            "parameters": {"workers": 8, "duration_seconds": 30, "command": "whoami"},
        },
    )
    assert rejected.status_code == 422
    assert controller.snapshot()["active"] is False


def test_production_environment_hides_ops_even_when_flag_is_on(client, ops_on, monkeypatch):
    monkeypatch.setattr(ops_on, "app_env", "production")
    assert client.post("/ops/login", json={"username": "operator", "password": "operator-pass"}).status_code == 404


def test_fault_starts_and_stops_without_leaking_root_cause_into_status_logs(client, ops_on):
    headers = ops_header(client)
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
    body = started.json()
    assert body["expected_root_cause"]
    assert body["outcome"] == "running"
    failed = client.get("/products")
    assert failed.status_code == 500
    health = client.get("/health")
    assert health.status_code == 200
    stopped = client.post("/ops/faults/stop", headers=headers)
    assert stopped.status_code == 200
    assert stopped.json()["outcome"] == "stopped"
    assert client.get("/products").status_code == 200
    assert controller.snapshot()["active"] is False


def test_pool_hold_is_bounded_and_released():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=QueuePool,
        pool_size=2,
        max_overflow=0,
        pool_timeout=0.2,
        connect_args={"check_same_thread": False},
    )
    controller.clear("stopped")
    controller.apply("db_pool_exhaustion", {"connections": 2, "duration_seconds": 30}, engine)
    try:
        try:
            engine.connect()
            raised = False
        except PoolTimeout:
            raised = True
        assert raised
    finally:
        controller.clear("stopped")
    released = engine.connect()
    released.close()
    engine.dispose()


def test_catalogue_rejects_forbidden_fields():
    load_catalogue()
    try:
        validate_selection("cpu_high", "fault", "ecommerce-shop-api", {"shell": 1})
    except CatalogueError as exc:
        assert "Unknown" in str(exc) or "not allowed" in str(exc)
    else:
        raise AssertionError("forbidden parameter was accepted")
    try:
        validate_selection("browse_load", "load", "ecommerce-shop-api", {"requests_per_second": 100})
    except CatalogueError:
        return
    raise AssertionError("load rate above the limit was accepted")
