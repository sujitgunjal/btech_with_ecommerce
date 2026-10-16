"""Tests for health-check endpoints."""


def test_health(client):
    """GET /health returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "incident-backend"
    assert data["checks"]["database"] is True


def test_liveness(client):
    """GET /health/live returns healthy without DB dependency."""
    response = client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "incident-backend"


def test_readiness(client):
    """GET /health/ready returns ready when DB is reachable."""
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["service"] == "incident-backend"
    assert data["checks"]["database"] is True
