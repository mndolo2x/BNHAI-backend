"""Draft, submit, and approve clinical notes for synthetic encounters."""
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import CLINICAL_READ, NOTE_WRITE, AuthenticatedUser, get_current_user
from app.auth.facility_scope import get_encounter_in_scope, get_note_in_scope
from app.db.models import ClinicalNoteRecord, EncounterRecord
from app.services.notifications import notify_facility_roles
from app.db.session import get_db
from app.models.clinical_note import (
    ClinicalNote,
    ClinicalNoteCreate,
    ClinicalNoteUpdate,
    NoteApprove,
    NoteStatus,
)
from app.models.encounter import EncounterStatus

router = APIRouter(tags=["Clinical Notes"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]

NOTE_TEXT_FIELDS = (
    "presenting_complaint",
    "history_of_present_illness",
    "relevant_history",
    "medications_and_allergies",
    "vitals",
    "examination",
    "assessment",
    "plan",
    "follow_up",
)


def _get_note_or_404(
    note_id: str, db: Session, user: AuthenticatedUser, required_roles: set[str]
) -> ClinicalNoteRecord:
    return get_note_in_scope(note_id, db, user, required_roles)


def _note_has_content(note: ClinicalNoteRecord) -> bool:
    return any((getattr(note, field) or "").strip() for field in NOTE_TEXT_FIELDS)


@router.post(
    "/encounters/{encounter_id}/notes",
    response_model=ClinicalNote,
    status_code=status.HTTP_201_CREATED,
    summary="Create a clinical note draft",
)
def create_note(
    encounter_id: str,
    payload: ClinicalNoteCreate,
    db: DbSession,
    user: CurrentUser,
) -> ClinicalNoteRecord:
    encounter = get_encounter_in_scope(encounter_id, db, user, NOTE_WRITE)
    if encounter.status != EncounterStatus.in_progress.value:
        raise HTTPException(status_code=409, detail="Notes can only be created for in-progress encounters")

    last_version = db.scalar(
        select(func.max(ClinicalNoteRecord.version)).where(
            ClinicalNoteRecord.encounter_id == encounter_id
        )
    ) or 0
    now = datetime.now(timezone.utc)
    fields = payload.model_dump()
    note = ClinicalNoteRecord(
        note_id=str(uuid4()),
        encounter_id=encounter_id,
        version=last_version + 1,
        status=NoteStatus.draft.value,
        created_at=now,
        updated_at=now,
        **fields,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.get(
    "/encounters/{encounter_id}/notes",
    response_model=list[ClinicalNote],
    summary="List note versions for an encounter",
)
def list_encounter_notes(encounter_id: str, db: DbSession, user: CurrentUser) -> list[ClinicalNoteRecord]:
    encounter = get_encounter_in_scope(encounter_id, db, user, CLINICAL_READ)
    statement = (
        select(ClinicalNoteRecord)
        .where(ClinicalNoteRecord.encounter_id == encounter_id)
        .order_by(ClinicalNoteRecord.version.desc())
    )
    return list(db.scalars(statement).all())


@router.get("/notes/{note_id}", response_model=ClinicalNote, summary="Get a clinical note")
def get_note(note_id: str, db: DbSession, user: CurrentUser) -> ClinicalNoteRecord:
    return _get_note_or_404(note_id, db, user, CLINICAL_READ)


@router.patch("/notes/{note_id}", response_model=ClinicalNote, summary="Edit an unapproved clinical note")
def update_note(
    note_id: str,
    payload: ClinicalNoteUpdate,
    db: DbSession,
    user: CurrentUser,
) -> ClinicalNoteRecord:
    note = _get_note_or_404(note_id, db, user, NOTE_WRITE)
    if note.status == NoteStatus.approved.value:
        raise HTTPException(status_code=409, detail="Approved notes cannot be edited; create a new note version")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one field to update")

    for field, value in changes.items():
        setattr(note, field, value)

    # Any change to a submitted note requires a fresh review.
    if note.status == NoteStatus.awaiting_review.value:
        note.status = NoteStatus.draft.value
        note.submitted_at = None

    note.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(note)
    return note


@router.post("/notes/{note_id}/submit-for-review", response_model=ClinicalNote, summary="Submit a note draft for review")
def submit_note_for_review(note_id: str, db: DbSession, user: CurrentUser) -> ClinicalNoteRecord:
    note = _get_note_or_404(note_id, db, user, NOTE_WRITE)
    if note.status != NoteStatus.draft.value:
        raise HTTPException(status_code=409, detail="Only draft notes can be submitted for review")
    if not _note_has_content(note):
        raise HTTPException(status_code=422, detail="Add content to at least one note section before submission")

    note.status = NoteStatus.awaiting_review.value
    encounter = db.get(EncounterRecord, note.encounter_id)
    if encounter is not None:
        notify_facility_roles(
            db,
            facility_id=encounter.facility_id,
            roles={"clinician", "facility_admin"},
            category="workflow",
            title="Clinical note awaiting review",
            message="A clinical note has been submitted and is awaiting review.",
            resource_type="clinical_notes",
            resource_id=note.note_id,
            exclude_user_id=user.user_id,
        )
    note.submitted_at = datetime.now(timezone.utc)
    note.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(note)
    return note


@router.post("/notes/{note_id}/approve", response_model=ClinicalNote, summary="Simulate approval of a reviewed note")
def approve_note(note_id: str, payload: NoteApprove, db: DbSession, user: CurrentUser) -> ClinicalNoteRecord:
    note = _get_note_or_404(note_id, db, user, NOTE_WRITE)
    if note.status != NoteStatus.awaiting_review.value:
        raise HTTPException(status_code=409, detail="Only notes awaiting review can be approved")

    now = datetime.now(timezone.utc)
    note.status = NoteStatus.approved.value
    note.approved_by = payload.reviewer_name
    note.approved_at = now
    note.updated_at = now
    db.commit()
    db.refresh(note)
    return note
