"""Cross-facility isolation tests using synthetic records only."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db.models import (
    ClinicalNoteRecord,
    EncounterRecord,
    FollowUpTaskRecord,
    LabObservationRecord,
    LabReportRecord,
    PatientRecord,
    UserFacilityRoleRecord,
)
from app.db.session import get_db


FACILITY_2_PATIENT = "DEMO-FACILITY-002-PATIENT"
FACILITY_2_ENCOUNTER = "DEMO-FACILITY-002-ENCOUNTER"
FACILITY_2_NOTE = "DEMO-FACILITY-002-NOTE"
FACILITY_2_REPORT = "DEMO-FACILITY-002-REPORT"
FACILITY_2_OBSERVATION = "DEMO-FACILITY-002-OBSERVATION"
FACILITY_2_FOLLOWUP = "DEMO-FACILITY-002-FOLLOWUP"


def _insert_facility_2_records(client: TestClient) -> None:
    """Insert one linked synthetic clinical record set in a different facility."""
    generator = client.app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        now = datetime.now(timezone.utc)
        patient = PatientRecord(
            patient_id=FACILITY_2_PATIENT,
            display_name="Synthetic Patient Facility Two",
            date_of_birth=None,
            record_status="active",
            facility_id="DEMO-FACILITY-002",
        )
        encounter = EncounterRecord(
            encounter_id=FACILITY_2_ENCOUNTER,
            patient_id=FACILITY_2_PATIENT,
            facility_id="DEMO-FACILITY-002",
            clinician_name="Synthetic Clinician",
            encounter_type="consultation",
            status="in_progress",
            started_at=now,
            updated_at=now,
        )
        note = ClinicalNoteRecord(
            note_id=FACILITY_2_NOTE,
            encounter_id=FACILITY_2_ENCOUNTER,
            version=1,
            author_name="Synthetic Clinician",
            status="draft",
            created_at=now,
            updated_at=now,
        )
        report = LabReportRecord(
            report_id=FACILITY_2_REPORT,
            patient_id=FACILITY_2_PATIENT,
            encounter_id=FACILITY_2_ENCOUNTER,
            source_system="SYNTHETIC-TEST-LIS",
            status="received",
            issued_at=None,
            received_at=now,
            updated_at=now,
            observations=[
                LabObservationRecord(
                    observation_id=FACILITY_2_OBSERVATION,
                    test_code="SYNTHETIC-TEST",
                    test_name="Synthetic test only",
                    value_numeric=1.0,
                    value_text=None,
                    unit="unit",
                    reference_range="synthetic reference",
                    interpretation=None,
                )
            ],
        )
        followup = FollowUpTaskRecord(
            task_id=FACILITY_2_FOLLOWUP,
            patient_id=FACILITY_2_PATIENT,
            report_id=FACILITY_2_REPORT,
            encounter_id=FACILITY_2_ENCOUNTER,
            description="Synthetic test follow-up only",
            assigned_to=None,
            status="open",
            due_at=None,
            outcome=None,
            created_at=now,
            updated_at=now,
            closed_at=None,
        )
        db.add(patient)
        db.commit()
        db.add(encounter)
        db.commit()
        db.add(note)
        db.commit()
        db.add(report)
        db.commit()
        db.add(followup)
        db.commit()
    finally:
        try:
            next(generator)
        except StopIteration:
            pass


def test_cross_facility_resources_are_hidden_from_other_facility(client: TestClient) -> None:
    _insert_facility_2_records(client)

    # Direct record lookups hide out-of-scope resources with 404.
    assert client.get(f"/api/v1/patients/{FACILITY_2_PATIENT}").status_code == 404
    assert client.get(f"/api/v1/encounters/{FACILITY_2_ENCOUNTER}").status_code == 404
    assert client.get(f"/api/v1/encounters/{FACILITY_2_ENCOUNTER}/notes").status_code == 404
    assert client.get(f"/api/v1/notes/{FACILITY_2_NOTE}").status_code == 404
    assert client.get(f"/api/v1/lab-results/{FACILITY_2_REPORT}").status_code == 404
    assert client.get(f"/api/v1/follow-ups/{FACILITY_2_FOLLOWUP}").status_code == 404

    # List endpoints must not leak the foreign facility through filters.
    assert client.get("/api/v1/patients", params={"search": FACILITY_2_PATIENT}).json() == []
    assert client.get("/api/v1/encounters", params={"patient_id": FACILITY_2_PATIENT}).json() == []
    assert client.get("/api/v1/lab-results", params={"patient_id": FACILITY_2_PATIENT}).json() == []
    assert client.get("/api/v1/follow-ups", params={"patient_id": FACILITY_2_PATIENT}).json() == []

    # Even audit-capable users may see only events tied to their assigned facility.
    audit = client.get(
        "/api/v1/audit-events",
        params={"resource_type": "patients", "resource_id": FACILITY_2_PATIENT},
    )
    assert audit.status_code == 200
    assert audit.json() == []

    # A write request cannot create a patient in an unassigned facility.
    create = client.post(
        "/api/v1/patients",
        json={
            "patient_id": "DEMO-UNAUTHORIZED-FACILITY-WRITE",
            "display_name": "Synthetic Denied Patient",
            "facility_id": "DEMO-FACILITY-002",
        },
    )
    assert create.status_code == 403

    cross_facility_encounter = client.post(
        "/api/v1/encounters",
        json={
            "patient_id": "DEMO-0001",
            "facility_id": "DEMO-FACILITY-002",
            "clinician_name": "Synthetic Clinician",
        },
    )
    assert cross_facility_encounter.status_code == 403

    cross_facility_note = client.post(
        f"/api/v1/encounters/{FACILITY_2_ENCOUNTER}/notes",
        json={"author_name": "Synthetic Clinician"},
    )
    assert cross_facility_note.status_code == 404

    cross_facility_lab = client.post(
        "/api/v1/lab-results",
        json={
            "patient_id": FACILITY_2_PATIENT,
            "source_system": "SYNTHETIC-TEST-LIS",
            "observations": [
                {"test_code": "SYNTHETIC", "test_name": "Synthetic only", "value_numeric": 1.0}
            ],
        },
    )
    assert cross_facility_lab.status_code == 404

    cross_facility_followup = client.post(
        "/api/v1/follow-ups",
        json={"patient_id": FACILITY_2_PATIENT, "description": "Synthetic test only"},
    )
    assert cross_facility_followup.status_code == 404

    # Out-of-scope resources cannot be modified by guessing their IDs.
    assert client.patch(
        f"/api/v1/lab-results/{FACILITY_2_REPORT}/status",
        json={"status": "validated"},
    ).status_code == 404
    assert client.patch(
        f"/api/v1/follow-ups/{FACILITY_2_FOLLOWUP}",
        json={"status": "in_progress"},
    ).status_code == 404


def test_role_must_be_assigned_at_the_same_facility(client: TestClient) -> None:
    """A clinician role at Facility 1 does not grant clinical access at Facility 2."""
    _insert_facility_2_records(client)

    generator = client.app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        # This user can read patient-directory records in Facility 2, but has no
        # clinical-read role there; the clinician role is assigned only in Facility 1.
        db.add(
            UserFacilityRoleRecord(
                assignment_id="ASSIGNMENT-TEST-CLINICIAN-F2-RECEPTIONIST",
                user_id="TEST-CLINICIAN",
                facility_id="DEMO-FACILITY-002",
                role="receptionist",
            )
        )
        db.commit()
    finally:
        try:
            next(generator)
        except StopIteration:
            pass

    from app.auth.security import create_access_token

    headers = {"Authorization": f"Bearer {create_access_token('TEST-CLINICIAN')}"}
    patient_response = client.get(f"/api/v1/patients/{FACILITY_2_PATIENT}", headers=headers)
    assert patient_response.status_code == 200

    encounter_response = client.get(f"/api/v1/encounters/{FACILITY_2_ENCOUNTER}", headers=headers)
    assert encounter_response.status_code == 404

    encounter_list = client.get(
        "/api/v1/encounters", params={"patient_id": FACILITY_2_PATIENT}, headers=headers
    )
    assert encounter_list.status_code == 200
    assert encounter_list.json() == []
