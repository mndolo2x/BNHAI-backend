"""Read-only listing of development audit events, scoped to assigned facilities."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import AUDIT_READ, AuthenticatedUser, get_current_user
from app.auth.facility_scope import assigned_facility_ids
from app.db.models import (
    AuditEventRecord,
    ClinicalNoteRecord,
    FacilityRecord,
    EncounterRecord,
    FollowUpTaskRecord,
    LabObservationRecord,
    LabReportRecord,
    PatientRecord,
    UserFacilityRoleRecord,
)
from app.db.session import get_db
from app.models.audit import AuditEvent

router = APIRouter(prefix="/audit-events", tags=["Audit Log"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


@router.get(
    "",
    response_model=list[AuditEvent],
    summary="List development audit events in assigned facilities",
    description=(
        "Lists successful database mutations for synthetic development records in the user's assigned facilities. "
        "Access requires an authenticated auditor, facility administrator, or platform administrator. "
        "This is not a production security audit system and must not be used with real patient data."
    ),
)
def list_audit_events(
    db: DbSession,
    user: CurrentUser,
    action: Literal["created", "updated", "deleted"] | None = Query(default=None),
    resource_type: str | None = Query(default=None, min_length=1, max_length=80),
    resource_id: str | None = Query(default=None, min_length=1, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[AuditEventRecord]:
    facilities = assigned_facility_ids(user, AUDIT_READ)

    # An audit event is visible only if its referenced resource can be tied to an
    # assigned facility. Unknown or platform-global resource types are hidden by default.
    scoped_resource_conditions = [
        and_(
            AuditEventRecord.resource_type == "patients",
            exists(
                select(1).select_from(PatientRecord).where(
                    PatientRecord.patient_id == AuditEventRecord.resource_id,
                    PatientRecord.facility_id.in_(facilities),
                )
            ),
        ),
        and_(
            AuditEventRecord.resource_type == "encounters",
            exists(
                select(1).select_from(EncounterRecord).where(
                    EncounterRecord.encounter_id == AuditEventRecord.resource_id,
                    EncounterRecord.facility_id.in_(facilities),
                )
            ),
        ),
        and_(
            AuditEventRecord.resource_type == "clinical_notes",
            exists(
                select(1)
                .select_from(ClinicalNoteRecord)
                .join(EncounterRecord, EncounterRecord.encounter_id == ClinicalNoteRecord.encounter_id)
                .where(
                    ClinicalNoteRecord.note_id == AuditEventRecord.resource_id,
                    EncounterRecord.facility_id.in_(facilities),
                )
            ),
        ),
        and_(
            AuditEventRecord.resource_type == "lab_reports",
            exists(
                select(1)
                .select_from(LabReportRecord)
                .join(PatientRecord, PatientRecord.patient_id == LabReportRecord.patient_id)
                .where(
                    LabReportRecord.report_id == AuditEventRecord.resource_id,
                    PatientRecord.facility_id.in_(facilities),
                )
            ),
        ),
        and_(
            AuditEventRecord.resource_type == "lab_observations",
            exists(
                select(1)
                .select_from(LabObservationRecord)
                .join(LabReportRecord, LabReportRecord.report_id == LabObservationRecord.report_id)
                .join(PatientRecord, PatientRecord.patient_id == LabReportRecord.patient_id)
                .where(
                    LabObservationRecord.observation_id == AuditEventRecord.resource_id,
                    PatientRecord.facility_id.in_(facilities),
                )
            ),
        ),
        and_(
            AuditEventRecord.resource_type == "follow_up_tasks",
            exists(
                select(1)
                .select_from(FollowUpTaskRecord)
                .join(PatientRecord, PatientRecord.patient_id == FollowUpTaskRecord.patient_id)
                .where(
                    FollowUpTaskRecord.task_id == AuditEventRecord.resource_id,
                    PatientRecord.facility_id.in_(facilities),
                )
            ),
        ),
        and_(
            AuditEventRecord.resource_type == "user_facility_roles",
            exists(
                select(1).select_from(UserFacilityRoleRecord).where(
                    UserFacilityRoleRecord.assignment_id == AuditEventRecord.resource_id,
                    UserFacilityRoleRecord.facility_id.in_(facilities),
                )
            ),
        ),
        and_(
            AuditEventRecord.resource_type == "facilities",
            exists(
                select(1).select_from(FacilityRecord).where(
                    FacilityRecord.facility_id == AuditEventRecord.resource_id,
                    FacilityRecord.facility_id.in_(facilities),
                )
            ),
        ),
        and_(
            AuditEventRecord.resource_type == "users",
            exists(
                select(1).select_from(UserFacilityRoleRecord).where(
                    UserFacilityRoleRecord.user_id == AuditEventRecord.resource_id,
                    UserFacilityRoleRecord.facility_id.in_(facilities),
                )
            ),
        ),
    ]

    statement = select(AuditEventRecord).where(or_(*scoped_resource_conditions))
    if action is not None:
        statement = statement.where(AuditEventRecord.action == action)
    if resource_type is not None and resource_type.strip():
        statement = statement.where(AuditEventRecord.resource_type == resource_type.strip())
    if resource_id is not None and resource_id.strip():
        statement = statement.where(AuditEventRecord.resource_id == resource_id.strip())
    statement = statement.order_by(
        AuditEventRecord.occurred_at.desc(), AuditEventRecord.event_id.desc()
    ).limit(limit)
    return list(db.scalars(statement).all())
