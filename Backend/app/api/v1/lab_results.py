"""Database-backed laboratory report and review workflow endpoints.

All records in this milestone are synthetic development data. Status changes are
workflow tracking only; this API does not interpret results or determine urgency.
"""
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth.dependencies import LAB_READ, LAB_WRITE, AuthenticatedUser, get_current_user
from app.auth.facility_scope import assigned_facility_ids, get_encounter_in_scope, get_lab_report_in_scope, get_patient_in_scope
from app.db.models import (
    EncounterRecord,
    FollowUpTaskRecord,
    LabObservationRecord,
    LabReportRecord,
    PatientRecord,
)
from app.db.session import get_db
from app.services.notifications import notify_facility_roles
from app.models.followup import FollowUpStatus
from app.models.lab_result import (
    LabReport,
    LabReportCreate,
    LabReportStatus,
    LabReportStatusUpdate,
)

router = APIRouter(prefix="/lab-results", tags=["Laboratory Results"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    LabReportStatus.received.value: {LabReportStatus.validated.value},
    LabReportStatus.validated.value: {LabReportStatus.awaiting_review.value},
    LabReportStatus.awaiting_review.value: {LabReportStatus.reviewed.value},
    LabReportStatus.reviewed.value: {
        LabReportStatus.follow_up_required.value,
        LabReportStatus.closed.value,
    },
    LabReportStatus.follow_up_required.value: {LabReportStatus.closed.value},
    LabReportStatus.closed.value: set(),
}


def _get_report_or_404(
    report_id: str, db: Session, user: AuthenticatedUser, required_roles: set[str]
) -> LabReportRecord:
    return get_lab_report_in_scope(report_id, db, user, required_roles)


@router.post(
    "",
    response_model=LabReport,
    status_code=status.HTTP_201_CREATED,
    summary="Register a synthetic laboratory report",
)
def create_lab_report(payload: LabReportCreate, db: DbSession, user: CurrentUser) -> LabReportRecord:
    patient = get_patient_in_scope(payload.patient_id, db, user, LAB_WRITE)

    if payload.encounter_id is not None:
        encounter = get_encounter_in_scope(payload.encounter_id, db, user, LAB_WRITE)
        if encounter.patient_id != payload.patient_id:
            raise HTTPException(
                status_code=409,
                detail="The encounter does not belong to the specified patient.",
            )

    now = datetime.now(timezone.utc)
    report = LabReportRecord(
        report_id=str(uuid4()),
        patient_id=payload.patient_id,
        encounter_id=payload.encounter_id,
        source_system=payload.source_system,
        status=LabReportStatus.received.value,
        issued_at=payload.issued_at,
        received_at=now,
        updated_at=now,
        observations=[
            LabObservationRecord(
                observation_id=str(uuid4()),
                test_code=item.test_code,
                test_name=item.test_name,
                value_numeric=item.value_numeric,
                value_text=item.value_text,
                unit=item.unit,
                reference_range=item.reference_range,
                interpretation=item.interpretation,
            )
            for item in payload.observations
        ],
    )
    db.add(report)
    notify_facility_roles(
        db,
        facility_id=patient.facility_id,
        roles={"clinician", "nurse", "facility_admin"},
        category="laboratory",
        title="New laboratory report received",
        message="A new laboratory report has been received and is available for authorised review.",
        resource_type="lab_reports",
        resource_id=report.report_id,
        exclude_user_id=user.user_id,
    )
    db.commit()
    db.refresh(report)
    return _get_report_or_404(report.report_id, db, user, LAB_WRITE)


@router.get("", response_model=list[LabReport], summary="List laboratory reports")
def list_lab_reports(
    db: DbSession,
    user: CurrentUser,
    patient_id: str | None = Query(default=None),
    report_status: LabReportStatus | None = Query(default=None, alias="status"),
) -> list[LabReportRecord]:
    statement = (
        select(LabReportRecord)
        .join(PatientRecord, PatientRecord.patient_id == LabReportRecord.patient_id)
        .outerjoin(EncounterRecord, EncounterRecord.encounter_id == LabReportRecord.encounter_id)
        .where(
            PatientRecord.facility_id.in_(assigned_facility_ids(user, LAB_READ)),
            or_(
                LabReportRecord.encounter_id.is_(None),
                and_(
                    EncounterRecord.encounter_id.is_not(None),
                    EncounterRecord.patient_id == LabReportRecord.patient_id,
                    EncounterRecord.facility_id == PatientRecord.facility_id,
                ),
            ),
        )
        .options(selectinload(LabReportRecord.observations))
    )
    if patient_id and patient_id.strip():
        statement = statement.where(LabReportRecord.patient_id == patient_id.strip())
    if report_status is not None:
        statement = statement.where(LabReportRecord.status == report_status.value)
    statement = statement.order_by(LabReportRecord.received_at.desc(), LabReportRecord.report_id)
    return list(db.scalars(statement).all())


@router.get("/{report_id}", response_model=LabReport, summary="Get a laboratory report")
def get_lab_report(report_id: str, db: DbSession, user: CurrentUser) -> LabReportRecord:
    return _get_report_or_404(report_id, db, user, LAB_READ)


@router.patch(
    "/{report_id}/status",
    response_model=LabReport,
    summary="Advance a laboratory report through its review workflow",
)
def update_lab_report_status(
    report_id: str,
    payload: LabReportStatusUpdate,
    db: DbSession,
    user: CurrentUser,
) -> LabReportRecord:
    report = _get_report_or_404(report_id, db, user, LAB_WRITE)
    new_status = payload.status.value
    old_status = report.status

    if new_status == old_status:
        return report
    if new_status not in ALLOWED_TRANSITIONS.get(old_status, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Invalid laboratory report status transition: {old_status} -> {new_status}",
        )

    if new_status == LabReportStatus.follow_up_required.value:
        active_task = db.scalar(
            select(FollowUpTaskRecord.task_id).where(
                FollowUpTaskRecord.report_id == report_id,
                FollowUpTaskRecord.status.notin_(
                    [FollowUpStatus.completed.value, FollowUpStatus.cancelled.value]
                ),
            ).limit(1)
        )
        if active_task is None:
            raise HTTPException(
                status_code=409,
                detail="Create an active follow-up task linked to this report before marking follow-up required.",
            )

    if new_status == LabReportStatus.closed.value:
        active_task = db.scalar(
            select(FollowUpTaskRecord.task_id).where(
                FollowUpTaskRecord.report_id == report_id,
                FollowUpTaskRecord.status.notin_(
                    [FollowUpStatus.completed.value, FollowUpStatus.cancelled.value]
                ),
            ).limit(1)
        )
        if active_task is not None:
            raise HTTPException(
                status_code=409,
                detail="All linked follow-up tasks must be completed or cancelled before closing this report.",
            )

    report.status = new_status
    report.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _get_report_or_404(report.report_id, db, user, LAB_WRITE)
