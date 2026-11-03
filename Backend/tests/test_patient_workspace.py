"""Tests for the consolidated, facility-scoped patient workspace."""

from fastapi.testclient import TestClient

from app.auth.security import create_access_token


def test_workspace_returns_patient_and_related_resources(client: TestClient) -> None:
    encounter_response = client.post(
        "/api/v1/encounters",
        json={
            "patient_id": "DEMO-0001",
            "facility_id": "DEMO-FACILITY-001",
            "clinician_name": "Synthetic Test Clinician",
            "encounter_type": "consultation",
        },
    )
    assert encounter_response.status_code == 201
    encounter_id = encounter_response.json()["encounter_id"]

    note_response = client.post(
        f"/api/v1/encounters/{encounter_id}/notes",
        json={
            "author_name": "Synthetic Test Clinician",
            "presenting_complaint": "Synthetic test complaint only",
        },
    )
    assert note_response.status_code == 201

    report_response = client.post(
        "/api/v1/lab-results",
        json={
            "patient_id": "DEMO-0001",
            "encounter_id": encounter_id,
            "source_system": "SYNTHETIC-TEST-LIS",
            "observations": [
                {
                    "test_code": "SYN-001",
                    "test_name": "Synthetic test measurement",
                    "value_numeric": 1.0,
                    "unit": "synthetic-unit",
                    "reference_range": "synthetic range",
                }
            ],
        },
    )
    assert report_response.status_code == 201
    report_id = report_response.json()["report_id"]

    for new_status in ("validated", "awaiting_review", "reviewed"):
        status_response = client.patch(
            f"/api/v1/lab-results/{report_id}/status", json={"status": new_status}
        )
        assert status_response.status_code == 200

    task_response = client.post(
        "/api/v1/follow-ups",
        json={
            "patient_id": "DEMO-0001",
            "report_id": report_id,
            "encounter_id": encounter_id,
            "description": "Synthetic follow-up task for automated testing",
        },
    )
    assert task_response.status_code == 201

    response = client.get("/api/v1/patients/DEMO-0001/workspace")
    assert response.status_code == 200
    payload = response.json()
    assert payload["patient"]["patient_id"] == "DEMO-0001"
    assert len(payload["encounters"]) == 1
    assert payload["encounters"][0]["encounter_id"] == encounter_id
    assert len(payload["clinical_notes"]) == 1
    assert payload["clinical_notes"][0]["presenting_complaint"] == "Synthetic test complaint only"
    assert len(payload["lab_reports"]) == 1
    assert payload["lab_reports"][0]["report_id"] == report_id
    assert len(payload["lab_reports"][0]["observations"]) == 1
    assert len(payload["follow_up_tasks"]) == 1
    assert payload["follow_up_tasks"][0]["report_id"] == report_id


def test_workspace_hides_patient_outside_assigned_facility(client: TestClient) -> None:
    response = client.get("/api/v1/patients/DEMO-0003/workspace")
    assert response.status_code == 404
    assert response.json()["detail"] == "Patient not found"


def test_workspace_requires_clinical_read_role(client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {create_access_token('TEST-RECEPTIONIST')}"}
    response = client.get("/api/v1/patients/DEMO-0001/workspace", headers=headers)
    assert response.status_code == 403


def test_workspace_for_unknown_patient_returns_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/patients/DEMO-NOT-FOUND/workspace")
    assert response.status_code == 404
