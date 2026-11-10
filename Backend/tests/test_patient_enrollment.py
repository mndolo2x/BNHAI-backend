
from uuid import uuid4

from app.auth.patient_enrollment import create_pending_patient_link
from app.auth.dependencies import AuthenticatedUser
from app.db.session import get_db
from app.main import app
from app.db.models import PatientAccountLinkRecord


def test_receptionist_creates_pending_patient_link(client):
    # Access the isolated test database.
    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        # Use the authenticated test receptionist.
        from app.db.models import UserFacilityRoleRecord

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


        assert isinstance(link, PatientAccountLinkRecord)
        assert link.verification_status == "pending"
        assert link.verified_at is None
        assert link.verified_by is None
        assert link.created_by == "TEST-RECEPTIONIST"


    finally:
        generator.close()



def test_cross_facility_enrollment_is_denied(client):
    from fastapi import HTTPException
    from app.db.models import UserFacilityRoleRecord
    from sqlalchemy import select

    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        assignments = db.query(UserFacilityRoleRecord).filter_by(
            user_id="TEST-OTHER-FACILITY-ADMIN"
        ).all()

        actor = AuthenticatedUser(
            user_id="TEST-OTHER-FACILITY-ADMIN",
            username="test_other_facility_admin",
            display_name="Other Facility Administrator",
            is_active=True,
            assignments=tuple(assignments),
        )

        try:
            create_pending_patient_link(
                db=db,
                actor=actor,
                user_id="TEST-PORTAL-PATIENT",
                patient_id="DEMO-0001",
            )
        except HTTPException as error:
            assert error.status_code == 404
        else:
            raise AssertionError(
                "Cross-facility enrollment was not denied"
            )

        link = db.scalar(
            select(PatientAccountLinkRecord).where(
                PatientAccountLinkRecord.user_id
                == "TEST-PORTAL-PATIENT",
                PatientAccountLinkRecord.patient_id
                == "DEMO-0001",
            )
        )

        assert link is None

    finally:
        generator.close()



def test_duplicate_patient_enrollment_is_rejected(client):
    import pytest
    from fastapi import HTTPException
    from app.db.models import UserFacilityRoleRecord

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

        first_link = create_pending_patient_link(
            db=db,
            actor=actor,
            user_id="TEST-PORTAL-PATIENT",
            patient_id="DEMO-0001",
        )

        first_link_id = first_link.link_id

        with pytest.raises(HTTPException) as error:
            create_pending_patient_link(
                db=db,
                actor=actor,
                user_id="TEST-PORTAL-PATIENT",
                patient_id="DEMO-0001",
            )

        assert error.value.status_code == 409

        links = db.query(PatientAccountLinkRecord).filter_by(
            user_id="TEST-PORTAL-PATIENT",
            patient_id="DEMO-0001",
        ).all()

        assert len(links) == 1
        assert links[0].link_id == first_link_id
        assert links[0].verification_status == "pending"

    finally:
        generator.close()




def test_patient_cannot_enroll_themselves(client):
    import pytest
    from fastapi import HTTPException
    from sqlalchemy import select

    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        actor = AuthenticatedUser(
            user_id="TEST-PORTAL-PATIENT",
            username="test_portal_patient",
            display_name="Test Portal Patient",
            is_active=True,
            assignments=(),
        )

        with pytest.raises(HTTPException) as error:
            create_pending_patient_link(
                db=db,
                actor=actor,
                user_id="TEST-PORTAL-PATIENT",
                patient_id="DEMO-0001",
            )

        assert error.value.status_code == 404

        link = db.scalar(
            select(PatientAccountLinkRecord).where(
                PatientAccountLinkRecord.user_id
                == "TEST-PORTAL-PATIENT",
                PatientAccountLinkRecord.patient_id
                == "DEMO-0001",
            )
        )

        assert link is None

    finally:
        generator.close()




def test_inactive_account_enrollment_is_rejected(client):
    import pytest
    from fastapi import HTTPException
    from sqlalchemy import select
    from app.db.models import UserRecord, UserFacilityRoleRecord

    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        target = db.get(UserRecord, "TEST-PORTAL-PATIENT")
        assert target is not None

        target.is_active = False
        db.commit()

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

        with pytest.raises(HTTPException) as error:
            create_pending_patient_link(
                db=db,
                actor=actor,
                user_id="TEST-PORTAL-PATIENT",
                patient_id="DEMO-0001",
            )

        assert error.value.status_code == 404

        link = db.scalar(
            select(PatientAccountLinkRecord).where(
                PatientAccountLinkRecord.user_id
                == "TEST-PORTAL-PATIENT",
                PatientAccountLinkRecord.patient_id
                == "DEMO-0001",
            )
        )

        assert link is None

    finally:
        generator.close()




def test_patient_enrollment_records_correct_audit_actor(client):
    from sqlalchemy import select
    from app.db.models import AuditEventRecord, UserFacilityRoleRecord

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

        audit_event = db.scalar(
            select(AuditEventRecord).where(
                AuditEventRecord.resource_type
                == "patient_account_links",
                AuditEventRecord.resource_id == link.link_id,
                AuditEventRecord.action == "created",
            )
        )

        assert audit_event is not None
        assert audit_event.actor_id == "TEST-RECEPTIONIST"
        assert audit_event.actor_source == "authenticated-user"
        assert audit_event.outcome == "success"

    finally:
        generator.close()
