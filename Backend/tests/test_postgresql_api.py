"""FastAPI integration tests against a dedicated PostgreSQL database."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.auth.security import create_access_token, hash_password
from app.db.models import FacilityRecord, UserRecord, UserFacilityRoleRecord
from app.db.session import get_db
from app.main import app


@pytest.fixture
def pg_client():
    url = os.getenv("BNHAI_TEST_DATABASE_URL")

    if not url:
        pytest.skip("BNHAI_TEST_DATABASE_URL is not configured")

    parsed = make_url(url)

    if (
        parsed.get_backend_name() != "postgresql"
        or parsed.database != "bnhai_test"
        or parsed.host not in ("127.0.0.1", "localhost")
        or parsed.port != 5432
        or parsed.username != "bnhai_test"
    ):
        pytest.fail("Unsafe PostgreSQL test database configuration")

    engine = create_engine(url, pool_pre_ping=True)
    connection = engine.connect()
    transaction = connection.begin()

    TestingSessionLocal = sessionmaker(
        bind=connection,
        autoflush=False,
        autocommit=False,
        join_transaction_mode="create_savepoint",
    )

    def override_get_db():
        with TestingSessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestingSessionLocal() as db:
            db.add(FacilityRecord(
                facility_id="PG-TEST-FACILITY",
                name="PostgreSQL Test Facility",
            ))
            db.add(UserRecord(
                user_id="PG-TEST-ADMIN",
                username="pg_test_admin",
                display_name="PostgreSQL Test Administrator",
                password_hash=hash_password("TestPassword123!"),
                is_active=True,
            ))
            db.flush()
            db.add(UserFacilityRoleRecord(
                assignment_id="PG-TEST-ADMIN-ROLE",
                user_id="PG-TEST-ADMIN",
                facility_id="PG-TEST-FACILITY",
                role="platform_admin",
            ))
            db.commit()

        with TestClient(
            app,
            headers={
                "Authorization": (
                    f"Bearer {create_access_token('PG-TEST-ADMIN')}"
                )
            },
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        try:
            transaction.rollback()
        finally:
            connection.close()
            engine.dispose()


def test_postgresql_api_readiness(pg_client: TestClient):
    response = pg_client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "ok",
    }


def test_postgresql_patient_creation_and_retrieval(pg_client: TestClient):
    """Verify patient writes and reads through the PostgreSQL API."""

    payload = {
        "patient_id": "PG-TEST-PATIENT-001",
        "display_name": "PostgreSQL Test Patient",
        "facility_id": "PG-TEST-FACILITY",
        "record_status": "active",
    }

    response = pg_client.post("/api/v1/patients", json=payload)

    assert response.status_code == 201
    assert response.json()["patient_id"] == payload["patient_id"]

    fetched = pg_client.get("/api/v1/patients/PG-TEST-PATIENT-001")

    assert fetched.status_code == 200
    assert fetched.json()["display_name"] == payload["display_name"]


def test_postgresql_encounter_creation_and_retrieval(pg_client: TestClient):
    """Verify encounter writes and reads through PostgreSQL."""

    patient = pg_client.post(
        "/api/v1/patients",
        json={
            "patient_id": "PG-TEST-ENCOUNTER-PATIENT",
            "display_name": "Synthetic Encounter Patient",
            "facility_id": "PG-TEST-FACILITY",
            "record_status": "active",
        },
    )
    assert patient.status_code == 201, patient.text

    response = pg_client.post(
        "/api/v1/encounters",
        json={
            "patient_id": "PG-TEST-ENCOUNTER-PATIENT",
            "facility_id": "PG-TEST-FACILITY",
            "clinician_name": "PostgreSQL Test Clinician",
            "encounter_type": "consultation",
        },
    )

    assert response.status_code == 201, response.text

    encounter = response.json()

    assert encounter["patient_id"] == "PG-TEST-ENCOUNTER-PATIENT"
    assert encounter["status"] == "in_progress"
    assert encounter["encounter_id"]

    fetched = pg_client.get(
        f"/api/v1/encounters/{encounter['encounter_id']}"
    )

    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["encounter_id"] == encounter["encounter_id"]


def test_postgresql_clinical_note_workflow(pg_client: TestClient):
    """Verify clinical note creation, review, and approval in PostgreSQL."""

    patient = pg_client.post(
        "/api/v1/patients",
        json={
            "patient_id": "PG-TEST-NOTE-PATIENT",
            "display_name": "Synthetic Clinical Notes Patient",
            "facility_id": "PG-TEST-FACILITY",
            "record_status": "active",
        },
    )
    assert patient.status_code == 201, patient.text

    encounter_response = pg_client.post(
        "/api/v1/encounters",
        json={
            "patient_id": "PG-TEST-NOTE-PATIENT",
            "facility_id": "PG-TEST-FACILITY",
            "clinician_name": "PostgreSQL Test Clinician",
            "encounter_type": "consultation",
        },
    )
    assert encounter_response.status_code == 201, encounter_response.text
    encounter_id = encounter_response.json()["encounter_id"]

    note_response = pg_client.post(
        f"/api/v1/encounters/{encounter_id}/notes",
        json={
            "author_name": "PostgreSQL Test Clinician",
            "presenting_complaint": "Synthetic test complaint",
            "history_of_present_illness": "Synthetic clinical history.",
        },
    )
    assert note_response.status_code == 201, note_response.text

    note = note_response.json()
    assert note["status"] == "draft"
    assert note["version"] == 1
    note_id = note["note_id"]

    submitted = pg_client.post(
        f"/api/v1/notes/{note_id}/submit-for-review"
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "awaiting_review"

    approved = pg_client.post(
        f"/api/v1/notes/{note_id}/approve",
        json={"reviewer_name": "PostgreSQL Test Reviewer"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_by"] == "PostgreSQL Test Reviewer"


def test_postgresql_lab_report_creation_and_retrieval(pg_client: TestClient):
    """Verify laboratory reports and observations in PostgreSQL."""

    patient = pg_client.post(
        "/api/v1/patients",
        json={
            "patient_id": "PG-TEST-LAB-PATIENT",
            "display_name": "Synthetic Laboratory Patient",
            "facility_id": "PG-TEST-FACILITY",
            "record_status": "active",
        },
    )
    assert patient.status_code == 201, patient.text

    encounter_response = pg_client.post(
        "/api/v1/encounters",
        json={
            "patient_id": "PG-TEST-LAB-PATIENT",
            "facility_id": "PG-TEST-FACILITY",
            "clinician_name": "PostgreSQL Test Clinician",
            "encounter_type": "consultation",
        },
    )
    assert encounter_response.status_code == 201, encounter_response.text

    encounter_id = encounter_response.json()["encounter_id"]

    report_response = pg_client.post(
        "/api/v1/lab-results",
        json={
            "patient_id": "PG-TEST-LAB-PATIENT",
            "encounter_id": encounter_id,
            "source_system": "PG-TEST-LIS",
            "issued_at": "2026-10-28T09:00:00Z",
            "observations": [
                {
                    "test_code": "HB",
                    "test_name": "Haemoglobin",
                    "value_numeric": 12.4,
                    "unit": "g/dL",
                    "reference_range": "Source-supplied range",
                },
                {
                    "test_code": "COMMENT",
                    "test_name": "Laboratory comment",
                    "value_text": "Synthetic laboratory observation",
                },
            ],
        },
    )

    assert report_response.status_code == 201, report_response.text

    report = report_response.json()

    assert report["patient_id"] == "PG-TEST-LAB-PATIENT"
    assert report["encounter_id"] == encounter_id
    assert report["status"] == "received"
    assert len(report["observations"]) == 2

    report_id = report["report_id"]

    fetched = pg_client.get(f"/api/v1/lab-results/{report_id}")

    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["report_id"] == report_id
    assert len(fetched.json()["observations"]) == 2


def test_postgresql_followup_workflow(pg_client: TestClient):
    """Verify follow-up task lifecycle in PostgreSQL."""
    patient = pg_client.post(
        "/api/v1/patients",
        json={
            "patient_id": "PG-TEST-FOLLOWUP-PATIENT",
            "display_name": "Synthetic Follow-up Patient",
            "facility_id": "PG-TEST-FACILITY",
            "record_status": "active",
        },
    )
    assert patient.status_code == 201, patient.text

    response = pg_client.post(
        "/api/v1/follow-ups",
        json={
            "patient_id": "PG-TEST-FOLLOWUP-PATIENT",
            "description": "Synthetic PostgreSQL follow-up",
            "assigned_to": "Test Nurse",
        },
    )
    assert response.status_code == 201, response.text

    task = response.json()
    assert task["status"] == "assigned"
    task_id = task["task_id"]

    started = pg_client.patch(
        f"/api/v1/follow-ups/{task_id}",
        json={"status": "in_progress"},
    )
    assert started.status_code == 200, started.text

    completed = pg_client.patch(
        f"/api/v1/follow-ups/{task_id}",
        json={
            "status": "completed",
            "outcome": "Synthetic outcome recorded",
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["closed_at"] is not None

    fetched = pg_client.get(f"/api/v1/follow-ups/{task_id}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["status"] == "completed"



def test_postgresql_bulk_invoice_batch(
    pg_client: TestClient, tmp_path, monkeypatch
):
    from io import BytesIO
    from reportlab.pdfgen import canvas

    monkeypatch.setenv(
        "CLAIMS_STORAGE_DIR",
        str(tmp_path / "claim-files"),
    )

    def make_pdf(invoice_number: str, amount: str) -> bytes:
        content = f"""Invoice Number: {invoice_number}
Member Surname and Initials: SMITH J
Patient First Name: JANE
Benefit Option: Standard
Membership Number: 123456789
Practice Code: 9914999
Practice Name: Example Medical Practice
Provider Name: Dr A Example
Date of Service: 29/10/2026
Nature of Service: General consultation
ICD-10: I10
Tariff Code: 0019
Quantity: 1
Amount: {amount}"""

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer)
        y = 800

        for line in content.splitlines():
            pdf.drawString(40, y, line)
            y -= 18

        pdf.showPage()
        pdf.save()
        return buffer.getvalue()

    response = pg_client.post(
        "/api/v1/claims/documents",
        data={"facility_id": "PG-TEST-FACILITY"},
        files=[
            (
                "files",
                ("invoice-001.pdf", make_pdf("PG-INV-001", "P450.00"), "application/pdf"),
            ),
            (
                "files",
                ("invoice-002.pdf", make_pdf("PG-INV-002", "P300.00"), "application/pdf"),
            ),
        ],
    )

    assert response.status_code == 201, response.text

    body = response.json()
    assert body["received_count"] == 2
    assert len(body["uploaded"]) == 2
    assert body["rejected"] == []

    documents = body["uploaded"]

    assert sorted(
        item["extracted_fields"]["amount"]
        for item in documents
    ) == [300.0, 450.0]

    for item in documents:
        document_id = item["claim_document_id"]

        corrected = pg_client.patch(
            f"/api/v1/claims/documents/{document_id}",
            json={
                "fields": {
                    "member_signature_confirmed": True,
                }
            },
        )

        assert corrected.status_code == 200, corrected.text

        approved = pg_client.post(
            f"/api/v1/claims/documents/{document_id}/approve",
            json={
                "member_signature_confirmed": True,
                "provider_signature_confirmed": True,
            },
        )

        assert approved.status_code == 200, approved.text
        assert approved.json()["claim_status"] == "approved"

    batch_response = pg_client.post(
        "/api/v1/claims/batches",
        json={
            "facility_id": "PG-TEST-FACILITY",
            "claim_document_ids": [
                item["claim_document_id"]
                for item in documents
            ],
        },
    )

    assert batch_response.status_code == 201, batch_response.text

    batch = batch_response.json()

    assert batch["document_count"] == 2
    assert batch["total_amount"] == 750.0
    assert batch["status"] == "prepared"

    detail = pg_client.get(
        f"/api/v1/claims/batches/{batch['batch_id']}"
    )

    assert detail.status_code == 200, detail.text
    assert detail.json()["document_count"] == 2



def test_postgresql_claim_batch_submission_tracking(
    pg_client: TestClient, tmp_path, monkeypatch
):
    from io import BytesIO
    from reportlab.pdfgen import canvas

    monkeypatch.setenv(
        "CLAIMS_STORAGE_DIR",
        str(tmp_path / "claim-files"),
    )

    content = """Invoice Number: PG-TRACK-001
Member Surname and Initials: SMITH J
Patient First Name: JANE
Benefit Option: Standard
Membership Number: 123456789
Practice Code: 9914999
Practice Name: Example Medical Practice
Provider Name: Dr A Example
Date of Service: 29/10/2026
Nature of Service: General consultation
ICD-10: I10
Tariff Code: 0019
Quantity: 1
Amount: P450.00"""

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    y = 800

    for line in content.splitlines():
        pdf.drawString(40, y, line)
        y -= 18

    pdf.showPage()
    pdf.save()

    uploaded = pg_client.post(
        "/api/v1/claims/documents",
        data={"facility_id": "PG-TEST-FACILITY"},
        files=[
            (
                "files",
                ("tracking-invoice.pdf", buffer.getvalue(), "application/pdf"),
            )
        ],
    )

    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["uploaded"][0]["claim_document_id"]

    corrected = pg_client.patch(
        f"/api/v1/claims/documents/{document_id}",
        json={
            "fields": {
                "member_signature_confirmed": True,
            }
        },
    )
    assert corrected.status_code == 200, corrected.text

    approved = pg_client.post(
        f"/api/v1/claims/documents/{document_id}/approve",
        json={
            "member_signature_confirmed": True,
            "provider_signature_confirmed": True,
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["claim_status"] == "approved"

    created = pg_client.post(
        "/api/v1/claims/batches",
        json={
            "facility_id": "PG-TEST-FACILITY",
            "claim_document_ids": [document_id],
        },
    )

    assert created.status_code == 201, created.text
    batch_id = created.json()["batch_id"]
    assert created.json()["status"] == "prepared"

    exported = pg_client.post(
        f"/api/v1/claims/batches/{batch_id}/export-review-csv"
    )

    assert exported.status_code == 200, exported.text
    assert "INTERNAL REVIEW EXPORT ONLY" in (
        exported.headers["x-bnhai-export-warning"]
    )
    assert b"PG-TRACK-001" in exported.content

    submitted = pg_client.post(
        f"/api/v1/claims/batches/{batch_id}/record-external-submission",
        json={
            "external_submission_reference": "PG-EMAIL-0001",
            "external_submission_channel": "email",
            "acknowledgement_notes": "Synthetic external submission.",
        },
    )

    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted_externally"

    acknowledged = pg_client.post(
        f"/api/v1/claims/batches/{batch_id}/record-acknowledgement",
        json={
            "outcome": "accepted",
            "notes": "Synthetic acceptance acknowledgement.",
        },
    )

    assert acknowledged.status_code == 200, acknowledged.text
    assert acknowledged.json()["status"] == "acknowledged"

    detail = pg_client.get(
        f"/api/v1/claims/batches/{batch_id}"
    )

    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "acknowledged"
    assert (
        detail.json()["external_submission_reference"]
        == "PG-EMAIL-0001"
    )
    assert (
        detail.json()["acknowledgement_notes"]
        == "Synthetic acceptance acknowledgement."
    )

