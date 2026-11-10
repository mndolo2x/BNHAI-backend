
"""Patient Portal endpoints for verified account holders."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.db.models import PatientAccountLinkRecord, PatientRecord
from app.db.session import get_db


router = APIRouter(prefix="/portal", tags=["Patient Portal"])

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


class PatientPortalProfile(BaseModel):
    user_id: str
    display_name: str
    patient_ids: list[str]


@router.get("/me", response_model=PatientPortalProfile)
def read_patient_portal_profile(
    db: DbSession,
    user: CurrentUser,
) -> PatientPortalProfile:
    """Return verified patient identifiers for the signed-in account."""

    statement = (
        select(PatientRecord.patient_id)
        .join(
            PatientAccountLinkRecord,
            PatientAccountLinkRecord.patient_id
            == PatientRecord.patient_id,
        )
        .where(
            PatientAccountLinkRecord.user_id == user.user_id,
            PatientAccountLinkRecord.verification_status == "verified",
            PatientRecord.record_status == "active",
        )
        .order_by(PatientRecord.patient_id)
    )

    patient_ids = list(db.scalars(statement).all())

    if not patient_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No verified patient account link is available.",
        )

    return PatientPortalProfile(
        user_id=user.user_id,
        display_name=user.display_name,
        patient_ids=patient_ids,
    )
