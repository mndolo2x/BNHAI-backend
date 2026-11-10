
import pytest
from fastapi import HTTPException

from app.auth.dependencies import AuthenticatedUser
from app.auth.patient_access import get_verified_patient_for_user
from app.auth.patient_enrollment import create_pending_patient_link
from app.auth.patient_identity_approval import approve_patient_identity
from app.auth.patient_identity_verification import record_patient_identity_check
from app.db.models import (
    PatientAccountLinkRecord,
    UserFacilityRoleRecord,
    UserRecord,
)
from app.db.session import get_db
from app.main import app


def _actor(db, user_id):
    user = db.get(UserRecord, user_id)
    assert user is not None
    roles = db.query(UserFacilityRoleRecord).filter_by(user_id=user_id).all()
    return AuthenticatedUser(
        user_id=user.user_id,
        username=user.username,
        display_name=user.display_name,
        is_active=user.is_active,
        assignments=tuple(roles),
    )


def test_independent_facility_admin_approves_verified_enrollment(client):
    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        receptionist = _actor(db, "TEST-RECEPTIONIST")
        administrator = _actor(db, "TEST-FACILITY-ADMIN")
        portal_user = _actor(db, "TEST-PORTAL-PATIENT")

        link = create_pending_patient_link(
            db=db,
            actor=receptionist,
            user_id=portal_user.user_id,
            patient_id="DEMO-0001",
        )
        assert link.created_by == receptionist.user_id

        record_patient_identity_check(
            db=db,
            actor=receptionist,
            link_id=link.link_id,
            verification_method="in_person_document_check",
        )

        # The patient must not have access before approval.
        with pytest.raises(HTTPException) as denied:
            get_verified_patient_for_user(
                "DEMO-0001", db, portal_user
            )
        assert denied.value.status_code == 404

        # A separate facility administrator approves the link.
        approved = approve_patient_identity(
            db=db,
            actor=administrator,
            link_id=link.link_id,
        )

        assert approved.verification_status == "verified"
        assert approved.verified_by == administrator.user_id
        assert approved.verified_at is not None

        # Confirm approval was saved to the database.
        db.expire_all()
        persisted = db.get(PatientAccountLinkRecord, link.link_id)

        assert persisted is not None
        assert persisted.verification_status == "verified"
        assert persisted.verified_by == "TEST-FACILITY-ADMIN"

        # The verified link now permits this patient lookup.
        patient = get_verified_patient_for_user(
            "DEMO-0001", db, portal_user
        )
        assert patient.patient_id == "DEMO-0001"

    finally:
        generator.close()




def test_administrator_cannot_approve_own_enrollment(client):
    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        administrator = _actor(db, "TEST-FACILITY-ADMIN")
        receptionist = _actor(db, "TEST-RECEPTIONIST")
        portal_user = _actor(db, "TEST-PORTAL-PATIENT")

        link = create_pending_patient_link(
            db=db,
            actor=administrator,
            user_id=portal_user.user_id,
            patient_id="DEMO-0001",
        )

        assert link.created_by == administrator.user_id

        # Another staff member performs the identity check.
        record_patient_identity_check(
            db=db,
            actor=receptionist,
            link_id=link.link_id,
            verification_method="in_person_document_check",
        )

        # Administrators cannot approve their own enrollments.
        with pytest.raises(HTTPException) as denied:
            approve_patient_identity(
                db=db,
                actor=administrator,
                link_id=link.link_id,
            )

        assert denied.value.status_code == 403

        db.expire_all()
        saved_link = db.get(
            PatientAccountLinkRecord,
            link.link_id,
        )

        assert saved_link.verification_status == "pending"
        assert saved_link.verified_at is None
        assert saved_link.verified_by is None

    finally:
        generator.close()



def test_other_facility_admin_cannot_approve_enrollment(client):
    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        receptionist = _actor(db, "TEST-RECEPTIONIST")
        other_admin = _actor(db, "TEST-OTHER-FACILITY-ADMIN")
        portal_user = _actor(db, "TEST-PORTAL-PATIENT")

        link = create_pending_patient_link(
            db=db,
            actor=receptionist,
            user_id=portal_user.user_id,
            patient_id="DEMO-0001",
        )

        record_patient_identity_check(
            db=db,
            actor=receptionist,
            link_id=link.link_id,
            verification_method="in_person_document_check",
        )

        # An administrator from another facility must be denied.
        with pytest.raises(HTTPException) as denied:
            approve_patient_identity(
                db=db,
                actor=other_admin,
                link_id=link.link_id,
            )

        assert denied.value.status_code == 404

        db.expire_all()
        saved_link = db.get(
            PatientAccountLinkRecord,
            link.link_id,
        )

        assert saved_link is not None
        assert saved_link.verification_status == "pending"
        assert saved_link.verified_at is None
        assert saved_link.verified_by is None

        # Denied approval must not grant portal access.
        with pytest.raises(HTTPException) as portal_denied:
            get_verified_patient_for_user(
                "DEMO-0001",
                db,
                portal_user,
            )

        assert portal_denied.value.status_code == 404

    finally:
        generator.close()




def test_approval_without_identity_evidence_is_rejected(client):
    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        receptionist = _actor(db, "TEST-RECEPTIONIST")
        administrator = _actor(db, "TEST-FACILITY-ADMIN")
        portal_user = _actor(db, "TEST-PORTAL-PATIENT")

        # Create enrollment without performing an identity check.
        link = create_pending_patient_link(
            db=db,
            actor=receptionist,
            user_id=portal_user.user_id,
            patient_id="DEMO-0001",
        )

        # Administrator attempts approval without verification evidence.
        with pytest.raises(HTTPException) as denied:
            approve_patient_identity(
                db=db,
                actor=administrator,
                link_id=link.link_id,
            )

        assert denied.value.status_code == 409

        # Enrollment must remain unchanged.
        db.expire_all()
        saved_link = db.get(
            PatientAccountLinkRecord,
            link.link_id,
        )

        assert saved_link is not None
        assert saved_link.verification_status == "pending"
        assert saved_link.verified_at is None
        assert saved_link.verified_by is None

        # Patient portal access must remain blocked.
        with pytest.raises(HTTPException) as portal_denied:
            get_verified_patient_for_user(
                "DEMO-0001",
                db,
                portal_user,
            )

        assert portal_denied.value.status_code == 404

    finally:
        generator.close()




def test_identity_verifier_cannot_approve_own_check(client):
    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        receptionist = _actor(db, "TEST-RECEPTIONIST")
        administrator = _actor(db, "TEST-FACILITY-ADMIN")
        portal_user = _actor(db, "TEST-PORTAL-PATIENT")

        # The receptionist initiates the enrollment.
        link = create_pending_patient_link(
            db=db,
            actor=receptionist,
            user_id=portal_user.user_id,
            patient_id="DEMO-0001",
        )

        # The administrator performs the identity check.
        verification = record_patient_identity_check(
            db=db,
            actor=administrator,
            link_id=link.link_id,
            verification_method="in_person_document_check",
        )

        assert verification.verified_by == administrator.user_id
        assert link.created_by == receptionist.user_id

        # The administrator must not approve their own check.
        with pytest.raises(HTTPException) as denied:
            approve_patient_identity(
                db=db,
                actor=administrator,
                link_id=link.link_id,
            )

        assert denied.value.status_code == 403

        # Confirm that approval was not recorded.
        db.expire_all()

        saved_link = db.get(
            PatientAccountLinkRecord,
            link.link_id,
        )

        assert saved_link is not None
        assert saved_link.verification_status == "pending"
        assert saved_link.verified_at is None
        assert saved_link.verified_by is None

    finally:
        generator.close()




def test_duplicate_patient_identity_approval_is_rejected(client):
    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        receptionist = _actor(db, "TEST-RECEPTIONIST")
        administrator = _actor(db, "TEST-FACILITY-ADMIN")
        portal_user = _actor(db, "TEST-PORTAL-PATIENT")

        link = create_pending_patient_link(
            db=db,
            actor=receptionist,
            user_id=portal_user.user_id,
            patient_id="DEMO-0001",
        )

        record_patient_identity_check(
            db=db,
            actor=receptionist,
            link_id=link.link_id,
            verification_method="in_person_document_check",
        )

        # First approval should succeed.
        first_approval = approve_patient_identity(
            db=db,
            actor=administrator,
            link_id=link.link_id,
        )

        assert first_approval.verification_status == "verified"
        assert first_approval.verified_at is not None

        first_approver_id = first_approval.verified_by
        first_verified_at = first_approval.verified_at

        # Second approval must be rejected.
        with pytest.raises(HTTPException) as denied:
            approve_patient_identity(
                db=db,
                actor=administrator,
                link_id=link.link_id,
            )

        assert denied.value.status_code == 409

        # Original approval information must remain unchanged.
        db.expire_all()

        persisted = db.get(
            PatientAccountLinkRecord,
            link.link_id,
        )

        assert persisted is not None
        assert persisted.verification_status == "verified"
        assert persisted.verified_by == first_approver_id
        assert persisted.verified_at == first_verified_at

    finally:
        generator.close()



def test_inactive_portal_account_cannot_be_approved(client):
    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        receptionist = _actor(db, "TEST-RECEPTIONIST")
        administrator = _actor(db, "TEST-FACILITY-ADMIN")
        portal_user = _actor(db, "TEST-PORTAL-PATIENT")

        link = create_pending_patient_link(
            db=db,
            actor=receptionist,
            user_id=portal_user.user_id,
            patient_id="DEMO-0001",
        )

        record_patient_identity_check(
            db=db,
            actor=receptionist,
            link_id=link.link_id,
            verification_method="in_person_document_check",
        )

        # Deactivate the portal account after identity verification.
        target = db.get(UserRecord, portal_user.user_id)
        assert target is not None
        target.is_active = False
        db.commit()

        # Administrator must not approve the inactive account.
        with pytest.raises(HTTPException) as denied:
            approve_patient_identity(
                db=db,
                actor=administrator,
                link_id=link.link_id,
            )

        assert denied.value.status_code == 409

        # Confirm the enrollment remains pending.
        db.expire_all()

        saved_link = db.get(
            PatientAccountLinkRecord,
            link.link_id,
        )

        assert saved_link is not None
        assert saved_link.verification_status == "pending"
        assert saved_link.verified_at is None
        assert saved_link.verified_by is None

    finally:
        generator.close()



def test_inactive_facility_administrator_cannot_approve(client):
    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        receptionist = _actor(db, "TEST-RECEPTIONIST")
        administrator = _actor(db, "TEST-FACILITY-ADMIN")
        portal_user = _actor(db, "TEST-PORTAL-PATIENT")

        link = create_pending_patient_link(
            db=db,
            actor=receptionist,
            user_id=portal_user.user_id,
            patient_id="DEMO-0001",
        )

        record_patient_identity_check(
            db=db,
            actor=receptionist,
            link_id=link.link_id,
            verification_method="in_person_document_check",
        )

        # Deactivate the administrator after authentication.
        staff = db.get(UserRecord, administrator.user_id)
        assert staff is not None
        staff.is_active = False
        db.commit()

        # Approval must be rejected.
        with pytest.raises(HTTPException) as denied:
            approve_patient_identity(
                db=db,
                actor=administrator,
                link_id=link.link_id,
            )

        assert denied.value.status_code == 403

        # Confirm the enrollment remains pending.
        db.expire_all()

        saved_link = db.get(
            PatientAccountLinkRecord,
            link.link_id,
        )

        assert saved_link is not None
        assert saved_link.verification_status == "pending"
        assert saved_link.verified_at is None
        assert saved_link.verified_by is None

    finally:
        generator.close()



def test_successful_approval_records_correct_audit_actor(client):
    from app.db.models import AuditEventRecord

    generator = app.dependency_overrides[get_db]()
    db = next(generator)

    try:
        receptionist = _actor(db, "TEST-RECEPTIONIST")
        administrator = _actor(db, "TEST-FACILITY-ADMIN")
        portal_user = _actor(db, "TEST-PORTAL-PATIENT")

        link = create_pending_patient_link(
            db=db,
            actor=receptionist,
            user_id=portal_user.user_id,
            patient_id="DEMO-0001",
        )

        record_patient_identity_check(
            db=db,
            actor=receptionist,
            link_id=link.link_id,
            verification_method="in_person_document_check",
        )

        approve_patient_identity(
            db=db,
            actor=administrator,
            link_id=link.link_id,
        )

        # Reload database state before inspecting audit events.
        db.expire_all()

        events = db.query(AuditEventRecord).filter_by(
            resource_type="patient_account_links",
            resource_id=link.link_id,
            action="updated",
            outcome="success",
        ).all()

        assert len(events) == 1
        assert events[0].actor_id == administrator.user_id
        assert events[0].actor_source == "authenticated-user"

    finally:
        generator.close()




def test_stale_session_cannot_overwrite_existing_approval(client):
    from app.db.models import AuditEventRecord

    first_generator = app.dependency_overrides[get_db]()
    second_generator = app.dependency_overrides[get_db]()

    db1 = next(first_generator)
    db2 = next(second_generator)

    try:
        receptionist = _actor(db1, "TEST-RECEPTIONIST")
        administrator = _actor(db1, "TEST-FACILITY-ADMIN")
        portal_user = _actor(db1, "TEST-PORTAL-PATIENT")

        link = create_pending_patient_link(
            db=db1,
            actor=receptionist,
            user_id=portal_user.user_id,
            patient_id="DEMO-0001",
        )

        link_id = link.link_id

        record_patient_identity_check(
            db=db1,
            actor=receptionist,
            link_id=link_id,
            verification_method="in_person_document_check",
        )

        # Session 2 reads the enrollment before approval.
        stale_link = db2.get(PatientAccountLinkRecord, link_id)

        assert stale_link is not None
        assert stale_link.verification_status == "pending"

        # Session 1 successfully approves.
        first_approval = approve_patient_identity(
            db=db1,
            actor=administrator,
            link_id=link_id,
        )

        assert first_approval.verification_status == "verified"

        original_approval_time = first_approval.verified_at

        # Session 2 must not approve the same enrollment again.
        with pytest.raises(HTTPException) as denied:
            approve_patient_identity(
                db=db2,
                actor=administrator,
                link_id=link_id,
            )

        assert denied.value.status_code == 409

        # Reload the final state from the database.
        db2.expire_all()

        persisted = db2.get(PatientAccountLinkRecord, link_id)

        assert persisted.verification_status == "verified"
        assert persisted.verified_by == administrator.user_id
        assert persisted.verified_at == original_approval_time

        # There must be exactly one successful approval audit.
        events = db2.query(AuditEventRecord).filter_by(
            resource_type="patient_account_links",
            resource_id=link_id,
            action="updated",
            outcome="success",
        ).all()

        assert len(events) == 1
        assert events[0].actor_id == administrator.user_id

    finally:
        first_generator.close()
        second_generator.close()




def test_simultaneous_approval_attempts_only_one_succeeds(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import sessionmaker
    from app.db.models import AuditEventRecord

    generator = app.dependency_overrides[get_db]()
    setup_db = next(generator)

    try:
        receptionist = _actor(setup_db, "TEST-RECEPTIONIST")
        portal_user = _actor(setup_db, "TEST-PORTAL-PATIENT")

        link = create_pending_patient_link(
            db=setup_db,
            actor=receptionist,
            user_id=portal_user.user_id,
            patient_id="DEMO-0001",
        )

        record_patient_identity_check(
            db=setup_db,
            actor=receptionist,
            link_id=link.link_id,
            verification_method="in_person_document_check",
        )

        link_id = link.link_id
        SessionFactory = sessionmaker(
            bind=setup_db.get_bind(),
            autoflush=False,
            autocommit=False,
        )
    finally:
        generator.close()

    start = Barrier(2)

    def attempt_approval():
        with SessionFactory() as worker_db:
            administrator = _actor(
                worker_db, "TEST-FACILITY-ADMIN"
            )

            # Start both approval attempts together.
            start.wait(timeout=10)

            try:
                approve_patient_identity(
                    db=worker_db,
                    actor=administrator,
                    link_id=link_id,
                )
                return 200
            except HTTPException as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        attempts = [
            executor.submit(attempt_approval)
            for _ in range(2)
        ]
        results = [
            attempt.result(timeout=30)
            for attempt in attempts
        ]

    print("Simultaneous approval outcomes:", results)

    # Exactly one approval must succeed.
    assert results.count(200) == 1, results

    # SQLite may return 503 if the database is temporarily locked.
    assert all(
        code in {200, 409, 503} for code in results
    ), results

    with SessionFactory() as verify_db:
        saved = verify_db.get(
            PatientAccountLinkRecord, link_id
        )

        assert saved is not None
        assert saved.verification_status == "verified"
        assert saved.verified_by == "TEST-FACILITY-ADMIN"
        assert saved.verified_at is not None

        # Exactly one successful approval audit event.
        audit_events = verify_db.query(
            AuditEventRecord
        ).filter_by(
            resource_type="patient_account_links",
            resource_id=link_id,
            action="updated",
            outcome="success",
        ).all()

        assert len(audit_events) == 1
        assert audit_events[0].actor_id == "TEST-FACILITY-ADMIN"
