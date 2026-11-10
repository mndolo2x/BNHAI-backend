
"""API-level security tests for the Patient Portal profile."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.security import create_access_token
from app.db.models import PatientAccountLinkRecord
from app.db.session import get_db
from app.main import app


def add_patient_link(
    user_id: str,
    patient_id: str,
    verification_status: str,
) -> None:
    """Insert a synthetic patient-account link."""
    session_generator = app.dependency_overrides[get_db]()
    db = next(session_generator)

    try:
        db.add(
            PatientAccountLinkRecord(
                link_id=str(uuid4()),
                user_id=user_id,
                patient_id=patient_id,
                verification_status=verification_status,
            )
        )
        db.commit()
    finally:
        session_generator.close()


def portal_request(client: TestClient, user_id: str):
    """Request the portal profile with a synthetic user's token."""
    return client.get(
        "/api/v1/portal/me",
        headers={
            "Authorization": f"Bearer {create_access_token(user_id)}"
        },
    )


def test_portal_rejects_invalid_token(client: TestClient) -> None:
    response = client.get(
        "/api/v1/portal/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


def test_portal_rejects_account_without_link(
    client: TestClient,
) -> None:
    response = portal_request(client, "TEST-CLINICIAN")
    assert response.status_code == 403


@pytest.mark.parametrize(
    "verification_status",
    ["pending", "revoked"],
)
def test_portal_rejects_unverified_links(
    client: TestClient,
    verification_status: str,
) -> None:
    add_patient_link(
        "TEST-CLINICIAN",
        "DEMO-0001",
        verification_status,
    )

    response = portal_request(client, "TEST-CLINICIAN")
    assert response.status_code == 403


def test_portal_returns_only_verified_patient_ids(
    client: TestClient,
) -> None:
    add_patient_link(
        "TEST-CLINICIAN",
        "DEMO-0001",
        "verified",
    )
    add_patient_link(
        "TEST-CLINICIAN",
        "DEMO-0002",
        "pending",
    )

    response = portal_request(client, "TEST-CLINICIAN")

    assert response.status_code == 200

    body = response.json()

    assert body["user_id"] == "TEST-CLINICIAN"
    assert body["patient_ids"] == ["DEMO-0001"]
    assert isinstance(body["display_name"], str)

    assert set(body) == {
        "user_id",
        "display_name",
        "patient_ids",
    }


def test_patient_account_has_no_staff_access(
    client: TestClient,
) -> None:
    """A patient account can authenticate but cannot use staff APIs."""

    token = create_access_token("TEST-PORTAL-PATIENT")
    headers = {"Authorization": f"Bearer {token}"}

    # The patient account exists and can authenticate.
    auth_response = client.get(
        "/api/v1/auth/me",
        headers=headers,
    )

    assert auth_response.status_code == 200
    assert auth_response.json()["user_id"] == "TEST-PORTAL-PATIENT"
    assert auth_response.json()["assignments"] == []

    # The patient cannot access the staff patient directory.
    staff_response = client.get(
        "/api/v1/patients",
        headers=headers,
    )

    assert staff_response.status_code == 403




def test_dedicated_patient_can_access_verified_portal(
    client: TestClient,
) -> None:
    """A patient-only account can access its verified portal profile."""

    add_patient_link(
        "TEST-PORTAL-PATIENT",
        "DEMO-0001",
        "verified",
    )

    response = portal_request(
        client,
        "TEST-PORTAL-PATIENT",
    )

    assert response.status_code == 200

    body = response.json()

    assert body["user_id"] == "TEST-PORTAL-PATIENT"
    assert body["display_name"] == "Test Portal Patient"
    assert body["patient_ids"] == ["DEMO-0001"]

    # Patient accounts must remain blocked from staff APIs.
    token = create_access_token("TEST-PORTAL-PATIENT")

    staff_response = client.get(
        "/api/v1/patients",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert staff_response.status_code == 403


def test_inactive_patient_is_excluded_from_portal_profile(client: TestClient) -> None:
    """An inactive patient record must not grant portal access."""
    from app.db.models import PatientRecord

    add_patient_link("TEST-PORTAL-PATIENT", "DEMO-0001", "verified")

    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        patient = db.get(PatientRecord, "DEMO-0001")
        assert patient is not None
        patient.record_status = "inactive"
        db.commit()
    finally:
        generator.close()

    response = portal_request(client, "TEST-PORTAL-PATIENT")
    assert response.status_code == 403, response.text
