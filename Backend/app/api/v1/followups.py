"""Follow-up task endpoints with validated workflow transitions."""
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import FOLLOW_UP_READ, FOLLOW_UP_WRITE, AuthenticatedUser, get_current_user
from app.auth.facility_scope import assigned_facility_ids, get_encounter_in_scope, get_followup_in_scope, get_lab_report_in_scope, get_patient_in_scope
from app.db.models import EncounterRecord, FollowUpTaskRecord, LabReportRecord, PatientRecord
from app.db.session import get_db
from app.models.followup import FollowUpCreate, FollowUpStatus, FollowUpTask, FollowUpUpdate
from app.services.notifications import notify_facility_roles

router = APIRouter(prefix="/follow-ups", tags=["Follow-up Tasks"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    FollowUpStatus.open.value: {
        FollowUpStatus.assigned.value,
        FollowUpStatus.in_progress.value,
        FollowUpStatus.escalated.value,
        FollowUpStatus.cancelled.value,
    },
    FollowUpStatus.assigned.value: {
        FollowUpStatus.open.value,
        FollowUpStatus.in_progress.value,
        FollowUpStatus.escalated.value,
        FollowUpStatus.cancelled.value,
    },
    FollowUpStatus.in_progress.value: {
        FollowUpStatus.assigned.value,
        FollowUpStatus.completed.value,
        FollowUpStatus.escalated.value,
        FollowUpStatus.cancelled.value,
    },
    FollowUpStatus.escalated.value: {
        FollowUpStatus.assigned.value,
        FollowUpStatus.in_progress.value,
        FollowUpStatus.completed.value,
        FollowUpStatus.cancelled.value,
    },
    FollowUpStatus.completed.value: set(),
    FollowUpStatus.cancelled.value: set(),
}


def _get_task_or_404(
    task_id: str, db: Session, user: AuthenticatedUser, required_roles: set[str]
) -> FollowUpTaskRecord:
    return get_followup_in_scope(task_id, db, user, required_roles)


@router.post(
    "",
    response_model=FollowUpTask,
    status_code=status.HTTP_201_CREATED,
    summary="Create a follow-up task",
)
def create_followup(payload: FollowUpCreate, db: DbSession, user: CurrentUser) -> FollowUpTaskRecord:
    patient = get_patient_in_scope(payload.patient_id, db, user, FOLLOW_UP_WRITE)

    report = None
    if payload.report_id is not None:
        report = get_lab_report_in_scope(payload.report_id, db, user, FOLLOW_UP_WRITE)
        if report.patient_id != payload.patient_id:
            raise HTTPException(status_code=409, detail="The report does not belong to the specified patient.")
        if report.status not in {"reviewed", "follow_up_required"}:
            raise HTTPException(
                status_code=409,
                detail="A laboratory follow-up task can only be linked after the report is reviewed.",
            )

    if payload.encounter_id is not None:
        encounter = get_encounter_in_scope(payload.encounter_id, db, user, FOLLOW_UP_WRITE)
        if encounter.patient_id != payload.patient_id:
            raise HTTPException(status_code=409, detail="The encounter does not belong to the specified patient.")
        if report is not None and report.encounter_id not in (None, payload.encounter_id):
            raise HTTPException(status_code=409, detail="The report is linked to a different encounter.")

    now = datetime.now(timezone.utc)
    task = FollowUpTaskRecord(
        task_id=str(uuid4()),
        patient_id=payload.patient_id,
        report_id=payload.report_id,
        encounter_id=payload.encounter_id,
        description=payload.description,
        assigned_to=payload.assigned_to,
        status=(FollowUpStatus.assigned.value if payload.assigned_to else FollowUpStatus.open.value),
        due_at=payload.due_at,
        outcome=None,
        created_at=now,
        updated_at=now,
        closed_at=None,
    )
    db.add(task)
    notify_facility_roles(
        db,
        facility_id=patient.facility_id,
        roles={"follow_up_worker", "nurse", "facility_admin"},
        category="follow_up",
        title="New follow-up task created",
        message="A follow-up task has been added to the facility work queue.",
        resource_type="follow_up_tasks",
        resource_id=task.task_id,
        exclude_user_id=user.user_id,
    )
    db.commit()
    db.refresh(task)
    return task


@router.get("", response_model=list[FollowUpTask], summary="List and filter follow-up tasks")
def list_followups(
    db: DbSession,
    user: CurrentUser,
    patient_id: str | None = Query(default=None),
    task_status: FollowUpStatus | None = Query(default=None, alias="status"),
    assigned_to: str | None = Query(default=None),
    overdue: bool = Query(default=False, description="Return due tasks that are not completed or cancelled"),
) -> list[FollowUpTaskRecord]:
    statement = (
        select(FollowUpTaskRecord)
        .join(PatientRecord, PatientRecord.patient_id == FollowUpTaskRecord.patient_id)
        .outerjoin(EncounterRecord, EncounterRecord.encounter_id == FollowUpTaskRecord.encounter_id)
        .outerjoin(LabReportRecord, LabReportRecord.report_id == FollowUpTaskRecord.report_id)
        .where(
            PatientRecord.facility_id.in_(assigned_facility_ids(user, FOLLOW_UP_READ)),
            or_(
                FollowUpTaskRecord.encounter_id.is_(None),
                and_(
                    EncounterRecord.encounter_id.is_not(None),
                    EncounterRecord.patient_id == FollowUpTaskRecord.patient_id,
                    EncounterRecord.facility_id == PatientRecord.facility_id,
                ),
            ),
            or_(
                FollowUpTaskRecord.report_id.is_(None),
                and_(
                    LabReportRecord.report_id.is_not(None),
                    LabReportRecord.patient_id == FollowUpTaskRecord.patient_id,
                ),
            ),
        )
    )
    if patient_id and patient_id.strip():
        statement = statement.where(FollowUpTaskRecord.patient_id == patient_id.strip())
    if task_status is not None:
        statement = statement.where(FollowUpTaskRecord.status == task_status.value)
    if assigned_to and assigned_to.strip():
        statement = statement.where(FollowUpTaskRecord.assigned_to == assigned_to.strip())
    if overdue:
        statement = statement.where(
            FollowUpTaskRecord.due_at < datetime.now(timezone.utc),
            FollowUpTaskRecord.status.notin_([FollowUpStatus.completed.value, FollowUpStatus.cancelled.value]),
        )
    statement = statement.order_by(FollowUpTaskRecord.due_at.is_(None), FollowUpTaskRecord.due_at, FollowUpTaskRecord.created_at)
    return list(db.scalars(statement).all())


@router.get("/{task_id}", response_model=FollowUpTask, summary="Get a follow-up task")
def get_followup(task_id: str, db: DbSession, user: CurrentUser) -> FollowUpTaskRecord:
    return _get_task_or_404(task_id, db, user, FOLLOW_UP_READ)


@router.patch("/{task_id}", response_model=FollowUpTask, summary="Update a follow-up task")
def update_followup(task_id: str, payload: FollowUpUpdate, db: DbSession, user: CurrentUser) -> FollowUpTaskRecord:
    task = _get_task_or_404(task_id, db, user, FOLLOW_UP_WRITE)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one field to update")

    old_status = task.status
    if old_status in {FollowUpStatus.completed.value, FollowUpStatus.cancelled.value}:
        raise HTTPException(status_code=409, detail="Completed or cancelled tasks cannot be changed.")

    if "assigned_to" in changes:
        task.assigned_to = changes["assigned_to"]
    if "due_at" in changes:
        task.due_at = changes["due_at"]
    if "outcome" in changes:
        task.outcome = changes["outcome"]

    requested_status = changes.get("status")
    new_status = requested_status.value if requested_status is not None else old_status
    if requested_status is None and "assigned_to" in changes:
        if task.assigned_to and old_status == FollowUpStatus.open.value:
            new_status = FollowUpStatus.assigned.value
        elif task.assigned_to is None and old_status == FollowUpStatus.assigned.value:
            new_status = FollowUpStatus.open.value

    if new_status != old_status and new_status not in ALLOWED_TRANSITIONS[old_status]:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Invalid follow-up task status transition: {old_status} -> {new_status}",
        )
    if new_status == FollowUpStatus.assigned.value and not task.assigned_to:
        db.rollback()
        raise HTTPException(status_code=422, detail="An assigned task must have an assignee.")
    if new_status == FollowUpStatus.completed.value and not (task.outcome or "").strip():
        db.rollback()
        raise HTTPException(status_code=422, detail="Record a follow-up outcome before completing the task.")

    task.status = new_status
    now = datetime.now(timezone.utc)
    task.updated_at = now
    if new_status in {FollowUpStatus.completed.value, FollowUpStatus.cancelled.value}:
        task.closed_at = now
    db.commit()
    db.refresh(task)
    return task
