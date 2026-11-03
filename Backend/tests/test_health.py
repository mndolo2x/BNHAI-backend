"""Tests for API health endpoints and OpenAPI documentation."""
from fastapi.testclient import TestClient


def test_health_live_returns_ok(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ready_confirms_database(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_openapi_documents_expected_routes(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Botswana National Healthcare AI Platform API"
    assert schema["info"]["version"] == "0.9.0"
    assert "/health/live" in schema["paths"]
    assert "/health/ready" in schema["paths"]
    assert "/api/v1/patients" in schema["paths"]
    assert "/api/v1/patients/{patient_id}" in schema["paths"]
    assert "/api/v1/patients/{patient_id}/workspace" in schema["paths"]
    assert "post" in schema["paths"]["/api/v1/patients"]
    assert "/api/v1/encounters" in schema["paths"]
    assert "/api/v1/encounters/{encounter_id}/notes" in schema["paths"]
    assert "/api/v1/notes/{note_id}/approve" in schema["paths"]
    assert "/api/v1/audit-events" in schema["paths"]


def test_swagger_docs_are_available(client: TestClient) -> None:
    response = client.get("/docs")
    assert response.status_code == 200
    assert "Swagger UI" in response.text
