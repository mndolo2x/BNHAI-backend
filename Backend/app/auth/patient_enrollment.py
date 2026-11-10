
"""Staff-controlled patient account enrollment."""

from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import PATIENT_WRITE, AuthenticatedUser
from app.auth.facility_scope import get_patient_in_scope
from app.db.models import PatientAccountLinkRecord, UserRecord


def create_pending_patient_link(
    db: Session,
    actor: AuthenticatedUser,
    user_id: str,
    patient_id: str,
) -> PatientAccountLinkRecord:
    """Create a pending link after staff facility authorization."""

    # Staff must have write permission at the patient's facility.
    get_patient_in_scope(patient_id, db, actor, PATIENT_WRITE)

    # The target account must exist and be active.
    target = db.get(UserRecord, user_id)
    if target is None or not target.is_active:
        raise HTTPException(
            status_code=404,
            detail="Account not found",
        )

    # Do not overwrite pending, verified, or revoked links.
    existing = db.scalar(
        select(PatientAccountLinkRecord).where(
            PatientAccountLinkRecord.user_id == user_id,
            PatientAccountLinkRecord.patient_id == patient_id,
        )
    )

    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Patient-account link already exists",
        )


    link = PatientAccountLinkRecord(
        link_id=str(uuid4()),
        user_id=user_id,
        patient_id=patient_id,
        created_by=actor.user_id,
        verification_status="pending",
        verified_at=None,
        verified_by=None,
    )


    # Attribute the mutation to the authenticated staff member.
    db.info["audit_actor_id"] = actor.user_id
    db.info["audit_actor_source"] = "authenticated-user"

    db.add(link)

    try:
        db.commit()
        db.refresh(link)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Unable to create patient-account link",
        ) from error

    return link
