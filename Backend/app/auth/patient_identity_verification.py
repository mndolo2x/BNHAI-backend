
"""Staff-attested identity checks for pending patient-account links."""

from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AuthenticatedUser,
    PATIENT_IDENTITY_VERIFY,
)
from app.auth.facility_scope import get_patient_in_scope
from app.db.models import (
    PatientAccountLinkRecord,
    PatientIdentityVerificationRecord,
    UserRecord,
    utc_now,
)


VERIFICATION_METHODS = {
    "in_person_document_check",
    "approved_remote_verification",
}


def record_patient_identity_check(
    db: Session,
    actor: AuthenticatedUser,
    link_id: str,
    verification_method: str,
) -> PatientIdentityVerificationRecord:
    """Record a staff identity-check attestation without granting portal access."""

    if not actor.is_active:
        raise HTTPException(
            status_code=403,
            detail="Inactive staff account",
        )

    if verification_method not in VERIFICATION_METHODS:
        raise HTTPException(
            status_code=422,
            detail="Unsupported verification method",
        )

    link = db.get(PatientAccountLinkRecord, link_id)

    if link is None:
        raise HTTPException(
            status_code=404,
            detail="Patient-account link not found",
        )

    # Enforce facility-specific staff authorization.
    get_patient_in_scope(
        link.patient_id,
        db,
        actor,
        PATIENT_IDENTITY_VERIFY,
    )

    if link.verification_status != "pending":
        raise HTTPException(
            status_code=409,
            detail="Enrollment is not pending",
        )

    if link.created_by is None:
        raise HTTPException(
            status_code=409,
            detail="Enrollment initiator is not recorded",
        )

    target = db.get(UserRecord, link.user_id)

    if target is None or not target.is_active:
        raise HTTPException(
            status_code=409,
            detail="Linked account is inactive or missing",
        )

    existing = db.scalar(
        select(PatientIdentityVerificationRecord).where(
            PatientIdentityVerificationRecord.link_id == link_id
        )
    )

    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Identity check already recorded",
        )

    verification = PatientIdentityVerificationRecord(
        verification_id=str(uuid4()),
        link_id=link_id,
        verification_method=verification_method,
        verified_by=actor.user_id,
        verified_at=utc_now(),
        verification_reference=str(uuid4()),
    )

    db.info["audit_actor_id"] = actor.user_id
    db.info["audit_actor_source"] = "authenticated-user"

    db.add(verification)

    try:
        db.commit()
        db.refresh(verification)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Unable to record identity check",
        ) from error

    return verification
