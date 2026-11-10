
"""Database integrity tests for patient-account links."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.db.models import PatientAccountLinkRecord
from app.db.session import get_db
from app.main import app


def test_create_patient_account_link(client: TestClient) -> None:
    """A valid account can be linked to an existing patient."""

    override = app.dependency_overrides[get_db]
    session_generator = override()
    db = next(session_generator)

    try:
        link_id = str(uuid4())

        link = PatientAccountLinkRecord(
            link_id=link_id,
            user_id="TEST-PLATFORM-ADMIN",
            patient_id="DEMO-0001",
            verification_status="pending",
        )

        db.add(link)
        db.commit()

        saved = db.get(PatientAccountLinkRecord, link_id)

        assert saved is not None
        assert saved.user_id == "TEST-PLATFORM-ADMIN"
        assert saved.patient_id == "DEMO-0001"
        assert saved.verification_status == "pending"

    finally:
        session_generator.close()


def test_duplicate_patient_account_link_rejected(
    client: TestClient,
) -> None:
    """The same account-patient pair cannot be linked twice."""

    override = app.dependency_overrides[get_db]
    session_generator = override()
    db = next(session_generator)

    try:
        for _ in range(2):
            db.add(
                PatientAccountLinkRecord(
                    link_id=str(uuid4()),
                    user_id="TEST-PLATFORM-ADMIN",
                    patient_id="DEMO-0001",
                    verification_status="pending",
                )
            )

        try:
            db.commit()
            assert False, "Duplicate account link was accepted"
        except IntegrityError:
            db.rollback()

    finally:
        session_generator.close()


@pytest.mark.parametrize(
    ("user_id", "patient_id", "verification_status"),
    [
        ("NONEXISTENT-USER", "DEMO-0001", "pending"),
        ("TEST-PLATFORM-ADMIN", "NONEXISTENT-PATIENT", "pending"),
        ("TEST-PLATFORM-ADMIN", "DEMO-0001", "invalid"),
    ],
)
def test_invalid_patient_account_links_rejected(
    client: TestClient,
    user_id: str,
    patient_id: str,
    verification_status: str,
) -> None:
    """Reject nonexistent references and invalid verification statuses."""

    override = app.dependency_overrides[get_db]
    session_generator = override()
    db = next(session_generator)

    try:
        link = PatientAccountLinkRecord(
            link_id=str(uuid4()),
            user_id=user_id,
            patient_id=patient_id,
            verification_status=verification_status,
        )

        db.add(link)

        with pytest.raises(IntegrityError):
            db.commit()

        db.rollback()

    finally:
        session_generator.close()
