"""Tests for encounter and clinical-note workflows using synthetic data."""
from fastapi.testclient import TestClient


def create_encounter(client: TestClient, patient_id: str = "DEMO-0001") -> dict:
    response = client.post(
        "/api/v1/encounters",
        json={
            "patient_id": patient_id,
            "facility_id": "DEMO-FACILITY-001",
            "clinician_name": "Demo Clinician",
            "encounter_type": "consultation",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_note(client: TestClient, encounter_id: str, **overrides) -> dict:
    payload = {
        "author_name": "Demo Clinician",
        "presenting_complaint": "Fictional test complaint",
        "history_of_present_illness": "Synthetic history entered for testing.",
    }
    payload.update(overrides)
    response = client.post(f"/api/v1/encounters/{encounter_id}/notes", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_encounter_returns_201_and_in_progress_status(client: TestClient) -> None:
    encounter = create_encounter(client)
    assert encounter["patient_id"] == "DEMO-0001"
    assert encounter["status"] == "in_progress"
    assert encounter["encounter_id"]
    assert encounter["started_at"]


def test_list_encounters_filters_by_patient_and_status(client: TestClient) -> None:
    create_encounter(client, "DEMO-0001")
    other = create_encounter(client, "DEMO-0002")
    client.patch(f"/api/v1/encounters/{other['encounter_id']}", json={"status": "completed"})

    by_patient = client.get("/api/v1/encounters", params={"patient_id": "DEMO-0001"})
    assert by_patient.status_code == 200
    assert len(by_patient.json()) == 1
    assert by_patient.json()[0]["patient_id"] == "DEMO-0001"

    by_status = client.get("/api/v1/encounters", params={"status": "completed"})
    assert by_status.status_code == 200
    assert len(by_status.json()) == 1
    assert by_status.json()[0]["encounter_id"] == other["encounter_id"]


def test_get_encounter_by_id(client: TestClient) -> None:
    encounter = create_encounter(client)
    response = client.get(f"/api/v1/encounters/{encounter['encounter_id']}")
    assert response.status_code == 200
    assert response.json()["encounter_id"] == encounter["encounter_id"]


def test_create_encounter_rejects_unknown_patient(client: TestClient) -> None:
    response = client.post(
        "/api/v1/encounters",
        json={
            "patient_id": "DEMO-9999",
            "facility_id": "DEMO-FACILITY-001",
            "clinician_name": "Demo Clinician",
        },
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Patient not found"}


def test_create_encounter_rejects_inactive_patient(client: TestClient) -> None:
    # Place the inactive test patient inside the authenticated user's facility so
    # this test reaches the inactive-record rule rather than facility isolation.
    from app.db.models import PatientRecord
    from app.db.session import get_db

    generator = client.app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        db.add(
            PatientRecord(
                patient_id="DEMO-INACTIVE-IN-SCOPE",
                display_name="Synthetic Inactive Patient",
                date_of_birth=None,
                record_status="inactive",
                facility_id="DEMO-FACILITY-001",
            )
        )
        db.commit()
    finally:
        try:
            next(generator)
        except StopIteration:
            pass

    response = client.post(
        "/api/v1/encounters",
        json={
            "patient_id": "DEMO-INACTIVE-IN-SCOPE",
            "facility_id": "DEMO-FACILITY-001",
            "clinician_name": "Demo Clinician",
        },
    )
    assert response.status_code == 409


def test_update_encounter_status_to_completed(client: TestClient) -> None:
    encounter = create_encounter(client)
    response = client.patch(
        f"/api/v1/encounters/{encounter['encounter_id']}",
        json={"status": "completed"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_completed_encounter_cannot_be_reopened(client: TestClient) -> None:
    encounter = create_encounter(client)
    client.patch(f"/api/v1/encounters/{encounter['encounter_id']}", json={"status": "completed"})
    response = client.patch(
        f"/api/v1/encounters/{encounter['encounter_id']}",
        json={"status": "in_progress"},
    )
    assert response.status_code == 409


def test_invalid_encounter_status_returns_422(client: TestClient) -> None:
    encounter = create_encounter(client)
    response = client.patch(
        f"/api/v1/encounters/{encounter['encounter_id']}",
        json={"status": "urgent"},
    )
    assert response.status_code == 422


def test_create_note_starts_as_draft(client: TestClient) -> None:
    encounter = create_encounter(client)
    note = create_note(client, encounter["encounter_id"])
    assert note["status"] == "draft"
    assert note["version"] == 1
    assert note["approved_by"] is None
    assert note["presenting_complaint"] == "Fictional test complaint"


def test_list_notes_for_encounter(client: TestClient) -> None:
    encounter = create_encounter(client)
    create_note(client, encounter["encounter_id"])
    response = client.get(f"/api/v1/encounters/{encounter['encounter_id']}/notes")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_update_draft_note(client: TestClient) -> None:
    encounter = create_encounter(client)
    note = create_note(client, encounter["encounter_id"])
    response = client.patch(
        f"/api/v1/notes/{note['note_id']}",
        json={"plan": "Synthetic plan text for testing."},
    )
    assert response.status_code == 200
    assert response.json()["plan"] == "Synthetic plan text for testing."
    assert response.json()["status"] == "draft"


def test_empty_note_cannot_be_submitted_for_review(client: TestClient) -> None:
    encounter = create_encounter(client)
    note = create_note(
        client,
        encounter["encounter_id"],
        presenting_complaint=None,
        history_of_present_illness=None,
    )
    response = client.post(f"/api/v1/notes/{note['note_id']}/submit-for-review")
    assert response.status_code == 422


def test_note_can_be_submitted_for_review(client: TestClient) -> None:
    encounter = create_encounter(client)
    note = create_note(client, encounter["encounter_id"])
    response = client.post(f"/api/v1/notes/{note['note_id']}/submit-for-review")
    assert response.status_code == 200
    assert response.json()["status"] == "awaiting_review"
    assert response.json()["submitted_at"] is not None


def test_draft_cannot_be_approved_without_submission(client: TestClient) -> None:
    encounter = create_encounter(client)
    note = create_note(client, encounter["encounter_id"])
    response = client.post(
        f"/api/v1/notes/{note['note_id']}/approve",
        json={"reviewer_name": "Demo Reviewer"},
    )
    assert response.status_code == 409


def test_note_can_be_approved_after_review_submission(client: TestClient) -> None:
    encounter = create_encounter(client)
    note = create_note(client, encounter["encounter_id"])
    client.post(f"/api/v1/notes/{note['note_id']}/submit-for-review")
    response = client.post(
        f"/api/v1/notes/{note['note_id']}/approve",
        json={"reviewer_name": "Demo Reviewer"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["approved_by"] == "Demo Reviewer"
    assert response.json()["approved_at"] is not None


def test_editing_submitted_note_returns_it_to_draft(client: TestClient) -> None:
    encounter = create_encounter(client)
    note = create_note(client, encounter["encounter_id"])
    client.post(f"/api/v1/notes/{note['note_id']}/submit-for-review")
    response = client.patch(
        f"/api/v1/notes/{note['note_id']}",
        json={"plan": "Updated synthetic plan."},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "draft"
    assert response.json()["submitted_at"] is None


def test_approved_note_cannot_be_edited(client: TestClient) -> None:
    encounter = create_encounter(client)
    note = create_note(client, encounter["encounter_id"])
    client.post(f"/api/v1/notes/{note['note_id']}/submit-for-review")
    client.post(
        f"/api/v1/notes/{note['note_id']}/approve",
        json={"reviewer_name": "Demo Reviewer"},
    )
    response = client.patch(
        f"/api/v1/notes/{note['note_id']}",
        json={"plan": "Attempt to edit an approved note."},
    )
    assert response.status_code == 409


def test_new_note_version_increments_without_overwriting_previous(client: TestClient) -> None:
    encounter = create_encounter(client)
    first = create_note(client, encounter["encounter_id"])
    second = create_note(client, encounter["encounter_id"], presenting_complaint="Second synthetic note version")
    assert first["version"] == 1
    assert second["version"] == 2
    response = client.get(f"/api/v1/encounters/{encounter['encounter_id']}/notes")
    assert [note["version"] for note in response.json()] == [2, 1]


def test_note_for_missing_encounter_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/encounters/not-a-real-encounter/notes",
        json={"author_name": "Demo Clinician", "presenting_complaint": "Synthetic text"},
    )
    assert response.status_code == 404


def test_notes_cannot_be_created_for_completed_encounter(client: TestClient) -> None:
    encounter = create_encounter(client)
    client.patch(f"/api/v1/encounters/{encounter['encounter_id']}", json={"status": "completed"})
    response = client.post(
        f"/api/v1/encounters/{encounter['encounter_id']}/notes",
        json={"author_name": "Demo Clinician", "presenting_complaint": "Synthetic text"},
    )
    assert response.status_code == 409


def test_note_update_rejects_null_author_name(client: TestClient) -> None:
    encounter = create_encounter(client)
    note = create_note(client, encounter["encounter_id"])
    response = client.patch(
        f"/api/v1/notes/{note['note_id']}",
        json={"author_name": None},
    )
    assert response.status_code == 422
