"""Facility-scoped operational dashboard aggregates."""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    AUDIT_READ, CLINICAL_READ, FOLLOW_UP_READ, LAB_READ, PATIENT_READ,
    AuthenticatedUser, get_current_user,
)
from app.auth.facility_scope import assigned_facility_ids
from app.db.models import (
    AuditEventRecord, ClinicalNoteRecord, EncounterRecord, FacilityRecord,
    FollowUpTaskRecord, LabReportRecord, PatientRecord, UserFacilityRoleRecord, UserRecord,
)
from app.db.session import get_db
from app.models.operational import DashboardActivity, DashboardSummary

router = APIRouter(prefix="/dashboard", tags=["Operational Dashboard"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


def _count(db: Session, statement) -> int:
    return int(db.scalar(statement) or 0)


def _scoped_activity_conditions(facilities: set[str]):
    """Only include audit rows that resolve to a record in the user's facilities."""
    return or_(
        and_(AuditEventRecord.resource_type == "patients", exists(
            select(1).select_from(PatientRecord).where(
                PatientRecord.patient_id == AuditEventRecord.resource_id,
                PatientRecord.facility_id.in_(facilities),
            )
        )),
        and_(AuditEventRecord.resource_type == "encounters", exists(
            select(1).select_from(EncounterRecord).where(
                EncounterRecord.encounter_id == AuditEventRecord.resource_id,
                EncounterRecord.facility_id.in_(facilities),
            )
        )),
        and_(AuditEventRecord.resource_type == "clinical_notes", exists(
            select(1).select_from(ClinicalNoteRecord)
            .join(EncounterRecord, EncounterRecord.encounter_id == ClinicalNoteRecord.encounter_id)
            .where(
                ClinicalNoteRecord.note_id == AuditEventRecord.resource_id,
                EncounterRecord.facility_id.in_(facilities),
            )
        )),
        and_(AuditEventRecord.resource_type == "lab_reports", exists(
            select(1).select_from(LabReportRecord)
            .join(PatientRecord, PatientRecord.patient_id == LabReportRecord.patient_id)
            .where(
                LabReportRecord.report_id == AuditEventRecord.resource_id,
                PatientRecord.facility_id.in_(facilities),
            )
        )),
        and_(AuditEventRecord.resource_type == "follow_up_tasks", exists(
            select(1).select_from(FollowUpTaskRecord)
            .join(PatientRecord, PatientRecord.patient_id == FollowUpTaskRecord.patient_id)
            .where(
                FollowUpTaskRecord.task_id == AuditEventRecord.resource_id,
                PatientRecord.facility_id.in_(facilities),
            )
        )),
        and_(AuditEventRecord.resource_type == "users", exists(
            select(1).select_from(UserFacilityRoleRecord).where(
                UserFacilityRoleRecord.user_id == AuditEventRecord.resource_id,
                UserFacilityRoleRecord.facility_id.in_(facilities),
            )
        )),
        and_(AuditEventRecord.resource_type == "facilities", exists(
            select(1).select_from(FacilityRecord).where(
                FacilityRecord.facility_id == AuditEventRecord.resource_id,
                FacilityRecord.facility_id.in_(facilities),
            )
        )),
    )


@router.get("/summary", response_model=DashboardSummary, summary="Get live operational metrics for assigned facilities")
def get_dashboard_summary(db: DbSession, user: CurrentUser) -> DashboardSummary:
    now = datetime.now(timezone.utc)
    all_facilities = {item.facility_id for item in user.assignments}
    patient_facilities = assigned_facility_ids(user, PATIENT_READ)
    clinical_facilities = assigned_facility_ids(user, CLINICAL_READ)
    lab_facilities = assigned_facility_ids(user, LAB_READ)
    followup_facilities = assigned_facility_ids(user, FOLLOW_UP_READ)
    audit_facilities = assigned_facility_ids(user, AUDIT_READ)

    patient_count = _count(db, select(func.count()).select_from(PatientRecord).where(
        PatientRecord.facility_id.in_(patient_facilities)
    )) if patient_facilities else 0
    active_patient_count = _count(db, select(func.count()).select_from(PatientRecord).where(
        PatientRecord.facility_id.in_(patient_facilities), PatientRecord.record_status == "active"
    )) if patient_facilities else 0
    encounters_in_progress = _count(db, select(func.count()).select_from(EncounterRecord).where(
        EncounterRecord.facility_id.in_(clinical_facilities), EncounterRecord.status == "in_progress"
    )) if clinical_facilities else 0
    notes_awaiting_review = _count(
        db,
        select(func.count()).select_from(ClinicalNoteRecord)
        .join(EncounterRecord, EncounterRecord.encounter_id == ClinicalNoteRecord.encounter_id)
        .where(
            EncounterRecord.facility_id.in_(clinical_facilities),
            ClinicalNoteRecord.status == "awaiting_review",
        ),
    ) if clinical_facilities else 0
    lab_reports_awaiting_review = _count(
        db,
        select(func.count()).select_from(LabReportRecord)
        .join(PatientRecord, PatientRecord.patient_id == LabReportRecord.patient_id)
        .where(
            PatientRecord.facility_id.in_(lab_facilities),
            LabReportRecord.status == "awaiting_review",
        ),
    ) if lab_facilities else 0
    active_task_states = ("open", "assigned", "in_progress", "escalated")
    follow_ups_open = _count(
        db,
        select(func.count()).select_from(FollowUpTaskRecord)
        .join(PatientRecord, PatientRecord.patient_id == FollowUpTaskRecord.patient_id)
        .where(
            PatientRecord.facility_id.in_(followup_facilities),
            FollowUpTaskRecord.status.in_(active_task_states),
        ),
    ) if followup_facilities else 0
    follow_ups_overdue = _count(
        db,
        select(func.count()).select_from(FollowUpTaskRecord)
        .join(PatientRecord, PatientRecord.patient_id == FollowUpTaskRecord.patient_id)
        .where(
            PatientRecord.facility_id.in_(followup_facilities),
            FollowUpTaskRecord.status.in_(active_task_states),
            FollowUpTaskRecord.due_at.is_not(None),
            FollowUpTaskRecord.due_at < now,
        ),
    ) if followup_facilities else 0

    recent_activity: list[DashboardActivity] = []
    if audit_facilities:
        rows = db.execute(
            select(AuditEventRecord, UserRecord.display_name)
            .outerjoin(UserRecord, UserRecord.user_id == AuditEventRecord.actor_id)
            .where(_scoped_activity_conditions(audit_facilities))
            .order_by(AuditEventRecord.occurred_at.desc(), AuditEventRecord.event_id.desc())
            .limit(10)
        ).all()
        recent_activity = [
            DashboardActivity(
                event_id=event.event_id,
                action=event.action,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                actor_display_name=display_name or "System or unknown actor",
                occurred_at=event.occurred_at,
            )
            for event, display_name in rows
        ]

    return DashboardSummary(
        generated_at=now,
        facility_count=len(all_facilities),
        patient_count=patient_count,
        active_patient_count=active_patient_count,
        encounters_in_progress=encounters_in_progress,
        notes_awaiting_review=notes_awaiting_review,
        lab_reports_awaiting_review=lab_reports_awaiting_review,
        follow_ups_open=follow_ups_open,
        follow_ups_overdue=follow_ups_overdue,
        recent_activity=recent_activity,
    )
