"""Tests for the database-backed synthetic patient API."""
from fastapi.testclient import TestClient


def test_list_patients_returns_synthetic_records(client: TestClient) -> None:
    response = client.get("/api/v1/patients")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["patient_id"] == "DEMO-0001"
    assert data[0]["display_name"] == "Demo Patient A"
    assert data[0]["record_status"] == "active"


def test_search_matches_display_name_case_insensitively(client: TestClient) -> None:
    response = client.get("/api/v1/patients", params={"search": "demo patient b"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["patient_id"] == "DEMO-0002"


def test_search_matches_demo_id(client: TestClient) -> None:
    response = client.get("/api/v1/patients", params={"search": "demo-0003"})
    assert response.status_code == 200
    assert response.json() == []  # DEMO-0003 belongs to another facility.


def test_filter_by_status(client: TestClient) -> None:
    response = client.get("/api/v1/patients", params={"record_status": "inactive"})
    assert response.status_code == 200
    data = response.json()
    assert data == []  # The inactive demo patient belongs to another facility.


def test_search_and_status_filter_can_be_combined(client: TestClient) -> None:
    response = client.get(
        "/api/v1/patients",
        params={"search": "demo", "record_status": "active"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(patient["record_status"] == "active" for patient in data)


def test_get_patient_by_id(client: TestClient) -> None:
    response = client.get("/api/v1/patients/DEMO-0002")
    assert response.status_code == 200
    assert response.json()["display_name"] == "Demo Patient B"


def test_missing_patient_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/patients/DEMO-9999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Patient not found"}


def test_invalid_status_filter_returns_422(client: TestClient) -> None:
    response = client.get("/api/v1/patients", params={"record_status": "unknown"})
    assert response.status_code == 422


def test_create_patient_persists_for_following_requests(client: TestClient) -> None:
    payload = {
        "patient_id": "DEMO-0004",
        "display_name": "Demo Patient D",
        "date_of_birth": "1998-05-17",
        "record_status": "active",
        "facility_id": "DEMO-FACILITY-001",
    }
    created = client.post("/api/v1/patients", json=payload)
    assert created.status_code == 201
    assert created.json()["patient_id"] == "DEMO-0004"

    fetched = client.get("/api/v1/patients/DEMO-0004")
    assert fetched.status_code == 200
    assert fetched.json()["display_name"] == "Demo Patient D"
    assert fetched.json()["date_of_birth"] == "1998-05-17"

    listed = client.get("/api/v1/patients")
    assert len(listed.json()) == 3


def test_duplicate_patient_id_returns_409(client: TestClient) -> None:
    payload = {
        "patient_id": "DEMO-0001",
        "display_name": "Different Demo Name",
        "facility_id": "DEMO-FACILITY-001",
    }
    response = client.post("/api/v1/patients", json=payload)
    assert response.status_code == 409
    assert response.json() == {"detail": "A patient with this ID already exists."}


def test_create_patient_rejects_blank_name(client: TestClient) -> None:
    payload = {
        "patient_id": "DEMO-0004",
        "display_name": "   ",
        "facility_id": "DEMO-FACILITY-001",
    }
    response = client.post("/api/v1/patients", json=payload)
    assert response.status_code == 422


def test_create_patient_rejects_unexpected_fields(client: TestClient) -> None:
    payload = {
        "patient_id": "DEMO-0004",
        "display_name": "Demo Patient D",
        "facility_id": "DEMO-FACILITY-001",
        "clinical_diagnosis": "Must not be accepted by this endpoint",
    }
    response = client.post("/api/v1/patients", json=payload)
    assert response.status_code == 422
