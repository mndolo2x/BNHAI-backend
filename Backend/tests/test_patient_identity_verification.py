
from app.auth.dependencies import AuthenticatedUser
from app.auth.patient_enrollment import create_pending_patient_link
from app.auth.patient_identity_verification import (
    record_patient_identity_check,
)
from app.db.models import (
    PatientAccountLinkRecord,
    PatientIdentityVerificationRecord,
    UserFacilityRoleRecord,
)
from app.db.session import get_db
from app.main import app


def test_receptionist_records_identity_check_without_approval(client):
    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        assignments = db.query(UserFacilityRoleRecord).filter_by(
            user_id="TEST-RECEPTIONIST"
        ).all()

        actor = AuthenticatedUser(
            user_id="TEST-RECEPTIONIST",
            username="test_receptionist",
            display_name="Test Receptionist",
            is_active=True,
            assignments=tuple(assignments),
        )

        link = create_pending_patient_link(
            db=db,
            actor=actor,
            user_id="TEST-PORTAL-PATIENT",
            patient_id="DEMO-0001",
        )

        verification = record_patient_identity_check(
            db=db,
            actor=actor,
            link_id=link.link_id,
            verification_method="in_person_document_check",
        )

        verification_id = verification.verification_id
        link_id = link.link_id

        db.expire_all()

        saved = db.get(
            PatientIdentityVerificationRecord,
            verification_id,
        )

        assert saved is not None
        assert saved.link_id == link_id
        assert saved.verified_by == "TEST-RECEPTIONIST"
        assert saved.verification_method == "in_person_document_check"
        assert saved.verification_reference

        saved_link = db.get(
            PatientAccountLinkRecord,
            link_id,
        )

        assert saved_link.verification_status == "pending"
        assert saved_link.verified_at is None
        assert saved_link.verified_by is None

    finally:
        generator.close()



def test_other_facility_cannot_record_identity_check(client):
    import pytest
    from fastapi import HTTPException

    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        receptionist_roles = db.query(UserFacilityRoleRecord).filter_by(
            user_id="TEST-RECEPTIONIST"
        ).all()

        receptionist = AuthenticatedUser(
            user_id="TEST-RECEPTIONIST",
            username="test_receptionist",
            display_name="Test Receptionist",
            is_active=True,
            assignments=tuple(receptionist_roles),
        )

        link = create_pending_patient_link(
            db=db,
            actor=receptionist,
            user_id="TEST-PORTAL-PATIENT",
            patient_id="DEMO-0001",
        )

        other_roles = db.query(UserFacilityRoleRecord).filter_by(
            user_id="TEST-OTHER-FACILITY-ADMIN"
        ).all()

        other_admin = AuthenticatedUser(
            user_id="TEST-OTHER-FACILITY-ADMIN",
            username="test_other_facility_admin",
            display_name="Other Facility Administrator",
            is_active=True,
            assignments=tuple(other_roles),
        )

        with pytest.raises(HTTPException) as error:
            record_patient_identity_check(
                db=db,
                actor=other_admin,
                link_id=link.link_id,
                verification_method="in_person_document_check",
            )

        assert error.value.status_code == 404

        db.expire_all()

        assert db.query(PatientIdentityVerificationRecord).filter_by(
            link_id=link.link_id
        ).one_or_none() is None

        assert db.get(
            PatientAccountLinkRecord,
            link.link_id,
        ).verification_status == "pending"

    finally:
        generator.close()



def test_duplicate_identity_check_is_rejected(client):
    import pytest
    from fastapi import HTTPException

    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        assignments = db.query(UserFacilityRoleRecord).filter_by(
            user_id="TEST-RECEPTIONIST"
        ).all()

        actor = AuthenticatedUser(
            user_id="TEST-RECEPTIONIST",
            username="test_receptionist",
            display_name="Test Receptionist",
            is_active=True,
            assignments=tuple(assignments),
        )

        link = create_pending_patient_link(
            db=db,
            actor=actor,
            user_id="TEST-PORTAL-PATIENT",
            patient_id="DEMO-0001",
        )

        first = record_patient_identity_check(
            db=db,
            actor=actor,
            link_id=link.link_id,
            verification_method="in_person_document_check",
        )

        with pytest.raises(HTTPException) as error:
            record_patient_identity_check(
                db=db,
                actor=actor,
                link_id=link.link_id,
                verification_method="in_person_document_check",
            )

        assert error.value.status_code == 409

        db.expire_all()

        saved = db.query(
            PatientIdentityVerificationRecord
        ).filter_by(
            link_id=link.link_id
        ).all()

        assert len(saved) == 1
        assert saved[0].verification_id == first.verification_id

        assert db.get(
            PatientAccountLinkRecord,
            link.link_id,
        ).verification_status == "pending"

    finally:
        generator.close()



def test_invalid_identity_verification_method_is_rejected(client):
    import pytest
    from fastapi import HTTPException

    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        assignments = db.query(UserFacilityRoleRecord).filter_by(
            user_id="TEST-RECEPTIONIST"
        ).all()

        actor = AuthenticatedUser(
            user_id="TEST-RECEPTIONIST",
            username="test_receptionist",
            display_name="Test Receptionist",
            is_active=True,
            assignments=tuple(assignments),
        )

        link = create_pending_patient_link(
            db=db,
            actor=actor,
            user_id="TEST-PORTAL-PATIENT",
            patient_id="DEMO-0001",
        )

        with pytest.raises(HTTPException) as error:
            record_patient_identity_check(
                db=db,
                actor=actor,
                link_id=link.link_id,
                verification_method="unapproved_method",
            )

        assert error.value.status_code == 422

        saved = db.query(
            PatientIdentityVerificationRecord
        ).filter_by(
            link_id=link.link_id
        ).all()

        assert saved == []

        db.refresh(link)
        assert link.verification_status == "pending"

    finally:
        generator.close()



def test_inactive_linked_account_cannot_be_identity_verified(client):
    import pytest
    from fastapi import HTTPException
    from app.db.models import UserRecord

    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        assignments = db.query(UserFacilityRoleRecord).filter_by(
            user_id="TEST-RECEPTIONIST"
        ).all()

        actor = AuthenticatedUser(
            user_id="TEST-RECEPTIONIST",
            username="test_receptionist",
            display_name="Test Receptionist",
            is_active=True,
            assignments=tuple(assignments),
        )

        link = create_pending_patient_link(
            db=db,
            actor=actor,
            user_id="TEST-PORTAL-PATIENT",
            patient_id="DEMO-0001",
        )

        # Deactivate the linked portal account.
        target = db.get(UserRecord, "TEST-PORTAL-PATIENT")
        assert target is not None
        target.is_active = False
        db.commit()

        # Verification must now be rejected.
        with pytest.raises(HTTPException) as error:
            record_patient_identity_check(
                db=db,
                actor=actor,
                link_id=link.link_id,
                verification_method="in_person_document_check",
            )

        assert error.value.status_code == 409

        # No identity verification record should exist.
        assert db.query(PatientIdentityVerificationRecord).filter_by(
            link_id=link.link_id
        ).one_or_none() is None

        # Enrollment must remain pending.
        db.refresh(link)
        assert link.verification_status == "pending"
        assert link.verified_at is None

    finally:
        generator.close()



def test_inactive_staff_cannot_record_identity_check(client):
    import pytest
    from fastapi import HTTPException

    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        assignments = db.query(UserFacilityRoleRecord).filter_by(
            user_id="TEST-RECEPTIONIST"
        ).all()

        active_actor = AuthenticatedUser(
            user_id="TEST-RECEPTIONIST",
            username="test_receptionist",
            display_name="Test Receptionist",
            is_active=True,
            assignments=tuple(assignments),
        )

        link = create_pending_patient_link(
            db=db,
            actor=active_actor,
            user_id="TEST-PORTAL-PATIENT",
            patient_id="DEMO-0001",
        )

        # Simulate an inactive staff account.
        inactive_actor = AuthenticatedUser(
            user_id="TEST-RECEPTIONIST",
            username="test_receptionist",
            display_name="Test Receptionist",
            is_active=False,
            assignments=tuple(assignments),
        )

        with pytest.raises(HTTPException) as error:
            record_patient_identity_check(
                db=db,
                actor=inactive_actor,
                link_id=link.link_id,
                verification_method="in_person_document_check",
            )

        assert error.value.status_code == 403

        # No verification record should be created.
        assert db.query(PatientIdentityVerificationRecord).filter_by(
            link_id=link.link_id
        ).one_or_none() is None

        db.refresh(link)
        assert link.verification_status == "pending"

    finally:
        generator.close()
