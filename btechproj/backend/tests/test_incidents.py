"""Tests for incident management endpoints."""

from tests.conftest import SAMPLE_INCIDENT, SAMPLE_INCIDENT_CRITICAL


# ---- Creation ----


def test_create_incident(client):
    """POST /incidents creates an incident and returns 201."""
    response = client.post("/incidents", json=SAMPLE_INCIDENT)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == SAMPLE_INCIDENT["title"]
    assert data["service"] == SAMPLE_INCIDENT["service"]
    assert data["severity"] == SAMPLE_INCIDENT["severity"]
    assert data["status"] == "created"
    assert data["external_id"].startswith("INC-")


def test_create_incident_missing_fields(client):
    """POST /incidents with missing required fields returns 422."""
    response = client.post("/incidents", json={"title": "incomplete"})
    assert response.status_code == 422


def test_create_incident_invalid_severity(client):
    """POST /incidents with invalid severity returns 422."""
    payload = {**SAMPLE_INCIDENT, "severity": "apocalyptic"}
    response = client.post("/incidents", json=payload)
    assert response.status_code == 422


# ---- Retrieval ----


def test_get_incident(client):
    """GET /incidents/{id} returns the created incident."""
    create_resp = client.post("/incidents", json=SAMPLE_INCIDENT)
    incident_id = create_resp.json()["id"]

    response = client.get(f"/incidents/{incident_id}")
    assert response.status_code == 200
    assert response.json()["id"] == incident_id


def test_get_incident_not_found(client):
    """GET /incidents/{id} with invalid ID returns 404."""
    response = client.get("/incidents/9999")
    assert response.status_code == 404


def test_list_incidents(client):
    """GET /incidents returns all incidents."""
    client.post("/incidents", json=SAMPLE_INCIDENT)
    client.post("/incidents", json=SAMPLE_INCIDENT_CRITICAL)

    response = client.get("/incidents")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["incidents"]) == 2


# ---- Filtering ----


def test_filter_by_service(client):
    """GET /incidents?service=... filters correctly."""
    client.post("/incidents", json=SAMPLE_INCIDENT)
    client.post("/incidents", json=SAMPLE_INCIDENT_CRITICAL)

    response = client.get("/incidents?service=order-service")
    data = response.json()
    assert data["total"] == 1
    assert data["incidents"][0]["service"] == "order-service"


def test_filter_by_severity(client):
    """GET /incidents?severity=... filters correctly."""
    client.post("/incidents", json=SAMPLE_INCIDENT)
    client.post("/incidents", json=SAMPLE_INCIDENT_CRITICAL)

    response = client.get("/incidents?severity=critical")
    data = response.json()
    assert data["total"] == 1
    assert data["incidents"][0]["severity"] == "critical"


def test_filter_by_status(client):
    """GET /incidents?status=... filters correctly."""
    client.post("/incidents", json=SAMPLE_INCIDENT)

    response = client.get("/incidents?status=created")
    data = response.json()
    assert data["total"] == 1

    response = client.get("/incidents?status=resolved")
    data = response.json()
    assert data["total"] == 0


# ---- Update / Resolve ----


def test_update_incident(client):
    """PATCH /incidents/{id} updates fields."""
    create_resp = client.post("/incidents", json=SAMPLE_INCIDENT)
    incident_id = create_resp.json()["id"]

    response = client.patch(
        f"/incidents/{incident_id}",
        json={"title": "Updated title", "severity": "critical"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated title"
    assert data["severity"] == "critical"


def test_update_incident_not_found(client):
    """PATCH /incidents/{id} with invalid ID returns 404."""
    response = client.patch(
        "/incidents/9999", json={"title": "nope"}
    )
    assert response.status_code == 404


def test_resolve_incident(client):
    """POST /incidents/{id}/resolve sets status to resolved."""
    create_resp = client.post("/incidents", json=SAMPLE_INCIDENT)
    incident_id = create_resp.json()["id"]

    response = client.post(f"/incidents/{incident_id}/resolve")
    assert response.status_code == 200
    assert response.json()["status"] == "resolved"
    assert response.json()["end_time"] is not None


def test_resolve_incident_not_found(client):
    """POST /incidents/{id}/resolve with invalid ID returns 404."""
    response = client.post("/incidents/9999/resolve")
    assert response.status_code == 404


# ---- Evidence (empty) ----


def test_get_evidence_empty(client):
    """GET /incidents/{id}/evidence returns unified evidence with empty arrays initially."""
    create_resp = client.post("/incidents", json=SAMPLE_INCIDENT)
    incident_id = create_resp.json()["id"]

    response = client.get(f"/incidents/{incident_id}/evidence")
    assert response.status_code == 200
    data = response.json()
    # Unified evidence response returns structured dict, not bare list
    assert isinstance(data, dict)
    assert "logs" in data
    assert "metrics" in data
    assert "traces" in data
    assert isinstance(data["logs"], list)
    assert isinstance(data["metrics"], list)
    assert isinstance(data["traces"], list)
    assert data["service"] == SAMPLE_INCIDENT["service"]


def test_get_evidence_legacy_format(client):
    """GET /incidents/{id}/evidence?format=legacy returns DB evidence rows."""
    create_resp = client.post("/incidents", json=SAMPLE_INCIDENT)
    incident_id = create_resp.json()["id"]

    response = client.get(f"/incidents/{incident_id}/evidence?format=legacy")
    assert response.status_code == 200
    assert response.json() == []


def test_get_evidence_not_found(client):
    """GET /incidents/{id}/evidence for unknown ID returns 404."""
    response = client.get("/incidents/9999/evidence")
    assert response.status_code == 404

