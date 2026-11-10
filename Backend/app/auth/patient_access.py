
"""Patient-specific authorization for the Patient Portal."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser
from app.db.models import PatientAccountLinkRecord, PatientRecord


def get_verified_patient_for_user(
    patient_id: str,
    db: Session,
    user: AuthenticatedUser,
) -> PatientRecord:
    """Return a patient only when the user has a verified link."""

    statement = (
        select(PatientRecord)
        .join(
            PatientAccountLinkRecord,
            PatientAccountLinkRecord.patient_id
            == PatientRecord.patient_id,
        )
        .where(
            PatientAccountLinkRecord.user_id == user.user_id,
            PatientAccountLinkRecord.patient_id == patient_id,
            PatientAccountLinkRecord.verification_status == "verified",
            PatientRecord.record_status == "active",
        )
    )

    patient = db.scalar(statement)

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail="Patient not found",
        )

    return patient
