
"""Tests for Patient Portal authorization."""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth.dependencies import AuthenticatedUser
from app.auth.patient_access import get_verified_patient_for_user
from app.db.models import PatientAccountLinkRecord
from app.db.session import get_db
from app.main import app


def make_test_user() -> AuthenticatedUser:
    """Create a synthetic authenticated identity."""
    return AuthenticatedUser(
        user_id="TEST-CLINICIAN",
        username="test_clinician",
        display_name="Test Clinician",
        is_active=True,
        assignments=(),
    )


def test_verified_patient_access(client: TestClient) -> None:
    """A verified link allows access only to its patient."""
    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        db.add(
            PatientAccountLinkRecord(
                link_id=str(uuid4()),
                user_id="TEST-CLINICIAN",
                patient_id="DEMO-0001",
                verification_status="verified",
            )
        )
        db.commit()

        user = make_test_user()

        patient = get_verified_patient_for_user(
            "DEMO-0001", db, user
        )
        assert patient.patient_id == "DEMO-0001"

        # The same account cannot access Patient B.
        with pytest.raises(HTTPException) as error:
            get_verified_patient_for_user(
                "DEMO-0002", db, user
            )

        assert error.value.status_code == 404

    finally:
        generator.close()


@pytest.mark.parametrize(
    "verification_status",
    ["pending", "revoked"],
)
def test_unverified_patient_access_denied(
    client: TestClient,
    verification_status: str,
) -> None:
    """Pending and revoked links must not grant access."""
    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        db.add(
            PatientAccountLinkRecord(
                link_id=str(uuid4()),
                user_id="TEST-CLINICIAN",
                patient_id="DEMO-0001",
                verification_status=verification_status,
            )
        )
        db.commit()

        with pytest.raises(HTTPException) as error:
            get_verified_patient_for_user(
                "DEMO-0001", db, make_test_user()
            )

        assert error.value.status_code == 404

    finally:
        generator.close()


def test_no_patient_link_denied(client: TestClient) -> None:
    """Accounts without a patient link cannot access records."""
    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        with pytest.raises(HTTPException) as error:
            get_verified_patient_for_user(
                "DEMO-0001", db, make_test_user()
            )

        assert error.value.status_code == 404

    finally:
        generator.close()


def test_inactive_patient_is_denied_even_with_verified_link(client: TestClient) -> None:
    """Verified account links must not unlock inactive patient records."""
    from app.db.models import PatientRecord

    generator = app.dependency_overrides[get_db]()
    db = next(generator)
    try:
        patient = db.get(PatientRecord, "DEMO-0001")
        assert patient is not None
        patient.record_status = "inactive"

        db.add(
            PatientAccountLinkRecord(
                link_id=str(uuid4()),
                user_id="TEST-CLINICIAN",
                patient_id="DEMO-0001",
                verification_status="verified",
            )
        )
        db.commit()

        with pytest.raises(HTTPException) as error:
            get_verified_patient_for_user(
                "DEMO-0001", db, make_test_user()
            )

        assert error.value.status_code == 404
    finally:
        generator.close()
