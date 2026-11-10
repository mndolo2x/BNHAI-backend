
"""Facility administrator approval of checked patient-account links."""

from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AuthenticatedUser,
    PATIENT_IDENTITY_APPROVE,
)
from app.auth.facility_scope import get_patient_in_scope
from app.db.models import (
    AuditEventRecord,
    PatientAccountLinkRecord,
    PatientIdentityVerificationRecord,
    UserRecord,
    utc_now,
)


def approve_patient_identity(
    db: Session,
    actor: AuthenticatedUser,
    link_id: str,
) -> PatientAccountLinkRecord:
    """Approve a checked enrollment exactly once, with an atomic audit record."""

    if not actor.is_active:
        raise HTTPException(status_code=403, detail="Inactive staff account")

    staff = db.get(UserRecord, actor.user_id)
    if staff is None or not staff.is_active:
        raise HTTPException(status_code=403, detail="Inactive or missing staff account")

    # PostgreSQL locks this row; SQLite needs the conditional UPDATE below.
    link = db.scalar(
        select(PatientAccountLinkRecord)
        .where(PatientAccountLinkRecord.link_id == link_id)
        .with_for_update()
    )

    if link is None:
        raise HTTPException(status_code=404, detail="Patient-account link not found")

    patient = get_patient_in_scope(
        link.patient_id, db, actor, PATIENT_IDENTITY_APPROVE
    )

    if patient.record_status != "active":
        raise HTTPException(status_code=409, detail="Patient record is not active")

    if link.verification_status != "pending":
        raise HTTPException(status_code=409, detail="Enrollment is not pending")

    if link.created_by is None:
        raise HTTPException(status_code=409, detail="Enrollment initiator is missing")

    if actor.user_id in {link.created_by, link.user_id}:
        raise HTTPException(status_code=403, detail="Self-approval is prohibited")

    target = db.get(UserRecord, link.user_id)

    if target is None or not target.is_active:
        raise HTTPException(status_code=409, detail="Linked account is inactive or missing")

    evidence = db.scalar(
        select(PatientIdentityVerificationRecord).where(
            PatientIdentityVerificationRecord.link_id == link_id
        )
    )

    if evidence is None:
        raise HTTPException(status_code=409, detail="Identity check is required")

    if evidence.verified_by == actor.user_id:
        raise HTTPException(status_code=403, detail="Verifier cannot approve own check")

    # Update only if the enrollment is STILL pending at write time.
    statement = (
        update(PatientAccountLinkRecord)
        .where(
            PatientAccountLinkRecord.link_id == link_id,
            PatientAccountLinkRecord.verification_status == "pending",
        )
        .values(
            verification_status="verified",
            verified_at=utc_now(),
            verified_by=actor.user_id,
        )
        .execution_options(synchronize_session=False)
    )

    db.info["audit_actor_id"] = actor.user_id
    db.info["audit_actor_source"] = "authenticated-user"

    try:
        result = db.execute(statement)

        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="Enrollment is no longer pending",
            )

        # Direct SQL updates bypass our ORM audit listener.
        # Add the audit event in the same database transaction.
        db.add(
            AuditEventRecord(
                event_id=str(uuid4()),
                actor_id=actor.user_id,
                actor_source="authenticated-user",
                action="updated",
                resource_type="patient_account_links",
                resource_id=link_id,
                outcome="success",
            )
        )

        db.commit()
        db.refresh(link)

    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Unable to approve enrollment",
        ) from error

    except OperationalError as error:
        db.rollback()

        if (
            db.get_bind().dialect.name == "sqlite"
            and "locked" in str(error.orig).lower()
        ):
            raise HTTPException(
                status_code=503,
                detail="Database temporarily busy; retry the request",
            ) from error

        raise

    return link
