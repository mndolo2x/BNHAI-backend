"""Database-backed clinical encounter endpoints for synthetic data, facility-scoped."""
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CLINICAL_READ, ENCOUNTER_WRITE, AuthenticatedUser, get_current_user
from app.auth.facility_scope import assigned_facility_ids, get_encounter_in_scope, get_patient_in_scope, require_assigned_facility
from app.db.models import EncounterRecord, PatientRecord
from app.db.session import get_db
from app.models.encounter import Encounter, EncounterCreate, EncounterStatus, EncounterStatusUpdate

router = APIRouter(prefix="/encounters", tags=["Encounters"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


@router.post("", response_model=Encounter, status_code=status.HTTP_201_CREATED, summary="Create an encounter")
def create_encounter(payload: EncounterCreate, db: DbSession, user: CurrentUser) -> EncounterRecord:
    """Create an encounter only at an assigned facility for a patient at that facility."""
    require_assigned_facility(user, payload.facility_id, ENCOUNTER_WRITE)
    patient = get_patient_in_scope(payload.patient_id, db, user, ENCOUNTER_WRITE)
    if patient.facility_id != payload.facility_id:
        raise HTTPException(status_code=409, detail="Patient and encounter must belong to the same facility.")
    if patient.record_status != "active":
        raise HTTPException(status_code=409, detail="Cannot start an encounter for an inactive record")

    now = datetime.now(timezone.utc)
    encounter = EncounterRecord(
        encounter_id=str(uuid4()),
        patient_id=payload.patient_id,
        facility_id=payload.facility_id,
        clinician_name=payload.clinician_name,
        encounter_type=payload.encounter_type,
        status=EncounterStatus.in_progress.value,
        started_at=now,
        updated_at=now,
    )
    db.add(encounter)
    db.commit()
    db.refresh(encounter)
    return encounter


@router.get("", response_model=list[Encounter], summary="List encounters in assigned facilities")
def list_encounters(
    db: DbSession,
    user: CurrentUser,
    patient_id: str | None = Query(default=None),
    encounter_status: EncounterStatus | None = Query(default=None, alias="status"),
) -> list[EncounterRecord]:
    statement = (
        select(EncounterRecord)
        .join(PatientRecord, PatientRecord.patient_id == EncounterRecord.patient_id)
        .where(
            EncounterRecord.facility_id.in_(assigned_facility_ids(user, CLINICAL_READ)),
            PatientRecord.facility_id == EncounterRecord.facility_id,
        )
    )
    if patient_id:
        statement = statement.where(EncounterRecord.patient_id == patient_id.strip())
    if encounter_status is not None:
        statement = statement.where(EncounterRecord.status == encounter_status.value)
    statement = statement.order_by(EncounterRecord.started_at.desc(), EncounterRecord.encounter_id)
    return list(db.scalars(statement).all())


@router.get("/{encounter_id}", response_model=Encounter, summary="Get an encounter")
def get_encounter(encounter_id: str, db: DbSession, user: CurrentUser) -> EncounterRecord:
    return get_encounter_in_scope(encounter_id, db, user, CLINICAL_READ)


@router.patch("/{encounter_id}", response_model=Encounter, summary="Update encounter status")
def update_encounter_status(
    encounter_id: str,
    payload: EncounterStatusUpdate,
    db: DbSession,
    user: CurrentUser,
) -> EncounterRecord:
    encounter = get_encounter_in_scope(encounter_id, db, user, ENCOUNTER_WRITE)
    new_status = payload.status.value
    if encounter.status != new_status and encounter.status != EncounterStatus.in_progress.value:
        raise HTTPException(
            status_code=409,
            detail="Completed or cancelled encounters cannot be reopened or changed.",
        )

    encounter.status = new_status
    encounter.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(encounter)
    return encounter
