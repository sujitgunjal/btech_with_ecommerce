"""Pytest setup. Environment is fixed before the application is imported."""

import os
import tempfile

_fd, _db_path = tempfile.mkstemp(suffix=".sqlite")
os.close(_fd)
os.environ["APP_ENV"] = "testing"
os.environ["FAULT_INJECTION_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///" + _db_path.replace("\\", "/")
os.environ["JWT_SECRET"] = "test-secret-key-for-northline-shop"
os.environ["OPS_USERNAME"] = "operator"
os.environ["OPS_PASSWORD"] = "operator-pass"
os.environ["PAYMENT_SERVICE_URL"] = ""
os.environ["PAYMENT_SHARED_SECRET"] = "test-payment-secret"
os.environ["INTERNAL_FAULT_TOKEN"] = "test-fault-token"
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = ""
os.environ["OTEL_SERVICE_NAME"] = "ecommerce-shop-api"
os.environ["LOAD_TEST_EMAIL"] = "loadbot@northline.shop"
os.environ["LOAD_TEST_PASSWORD"] = "LoadbotPass123!"

import pytest
from fastapi.testclient import TestClient

from shop_api.database import Base, engine
from shop_api.main import app
from shop_api.services.load import runner
from shop_platform.faults import controller


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    controller.clear("stopped")
    runner.stop()
    runner.send = None
    with TestClient(app) as test_client:
        yield test_client
    controller.clear("stopped")
    runner.stop()
    runner.send = None


@pytest.fixture
def ops_on(monkeypatch):
    from shop_platform.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "fault_injection_enabled", True)
    monkeypatch.setattr(settings, "app_env", "testing")
    return settings


def auth_header(client, email="demo@northline.shop", password="DemoPass123!"):
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def ops_header(client):
    response = client.post("/ops/login", json={"username": "operator", "password": "operator-pass"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
