"""Database-backed patient-directory endpoints with facility scoping."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import PATIENT_READ, PATIENT_WRITE, AuthenticatedUser, get_current_user
from app.auth.facility_scope import assigned_facility_ids, get_patient_in_scope, require_assigned_facility
from app.db.models import PatientRecord
from app.db.session import get_db
from app.models.patient import Patient, PatientCreate, PatientStatus

router = APIRouter(prefix="/patients", tags=["Patients"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


@router.get("", response_model=list[Patient], summary="List patients in assigned facilities")
def list_patients(
    db: DbSession,
    user: CurrentUser,
    search: str | None = Query(default=None, description="Search by demo ID or display name"),
    record_status: PatientStatus | None = Query(default=None, description="Filter by administrative record status"),
) -> list[PatientRecord]:
    """Return only patient records belonging to one of the user's assigned facilities."""
    facilities = assigned_facility_ids(user, PATIENT_READ)
    statement = select(PatientRecord).where(PatientRecord.facility_id.in_(facilities))

    if search and search.strip():
        term = search.strip().casefold()
        statement = statement.where(
            or_(
                func.lower(PatientRecord.patient_id).contains(term),
                func.lower(PatientRecord.display_name).contains(term),
            )
        )

    if record_status is not None:
        statement = statement.where(PatientRecord.record_status == record_status.value)

    statement = statement.order_by(PatientRecord.patient_id)
    return list(db.scalars(statement).all())


@router.post(
    "",
    response_model=Patient,
    status_code=status.HTTP_201_CREATED,
    summary="Create a patient record in an assigned facility",
)
def create_patient(payload: PatientCreate, db: DbSession, user: CurrentUser) -> PatientRecord:
    """Create a synthetic patient record only in an explicitly assigned facility."""
    require_assigned_facility(user, payload.facility_id, PATIENT_WRITE)
    record = PatientRecord(**payload.model_dump(mode="python"))
    db.add(record)
    try:
        db.commit()
        db.refresh(record)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A patient with this ID already exists.",
        ) from error
    return record


@router.get("/{patient_id}", response_model=Patient, summary="Get a patient in an assigned facility")
def get_patient(patient_id: str, db: DbSession, user: CurrentUser) -> PatientRecord:
    """Return a patient only when their facility is assigned to the current user."""
    return get_patient_in_scope(patient_id, db, user, PATIENT_READ)
