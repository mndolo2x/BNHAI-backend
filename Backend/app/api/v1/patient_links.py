
"""Staff-only patient enrollment, identity verification, and approval endpoints."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.auth.patient_enrollment import create_pending_patient_link
from app.auth.patient_identity_verification import record_patient_identity_check
from app.auth.patient_identity_approval import approve_patient_identity
from app.db.session import get_db


router = APIRouter(prefix="/patient-links", tags=["Patient Account Links"])

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


class PatientLinkCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)
    patient_id: str = Field(min_length=1, max_length=40)


class PatientLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    link_id: str
    user_id: str
    patient_id: str
    created_by: str | None
    verification_status: Literal["pending", "verified", "revoked"]
    verified_by: str | None
    verified_at: datetime | None


class IdentityCheckCreate(BaseModel):
    verification_method: Literal[
        "in_person_document_check", "approved_remote_verification"
    ]


class IdentityCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    verification_id: str
    link_id: str
    verification_method: str
    verified_by: str
    verified_at: datetime


@router.post(
    "",
    response_model=PatientLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_patient_link(
    payload: PatientLinkCreate,
    db: DbSession,
    actor: CurrentUser,
):
    """Create a pending patient-account enrollment."""
    return create_pending_patient_link(
        db, actor, payload.user_id, payload.patient_id
    )


@router.post(
    "/{link_id}/verify-identity",
    response_model=IdentityCheckResponse,
    status_code=status.HTTP_201_CREATED,
)
def verify_patient_link_identity(
    link_id: str,
    payload: IdentityCheckCreate,
    db: DbSession,
    actor: CurrentUser,
):
    """Record an identity check without approving portal access."""
    return record_patient_identity_check(
        db, actor, link_id, payload.verification_method
    )


@router.post(
    "/{link_id}/approve",
    response_model=PatientLinkResponse,
)
def approve_patient_link(
    link_id: str,
    db: DbSession,
    actor: CurrentUser,
):
    """Approve a checked enrollment following independent authorization."""
    return approve_patient_identity(db, actor, link_id)
