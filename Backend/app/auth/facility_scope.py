"""Facility-level access helpers for clinical resources.

A user's permission must be assigned at the same facility as the requested
resource. Resources outside that role/facility scope return 404 to avoid
confirming their existence. This is a prototype control, not a production
security certification.
"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth.dependencies import (
    AUDIT_READ,
    CLINICAL_READ,
    ENCOUNTER_WRITE,
    FOLLOW_UP_READ,
    FOLLOW_UP_WRITE,
    LAB_READ,
    LAB_WRITE,
    NOTE_WRITE,
    PATIENT_READ,
    PATIENT_WRITE,
    AuthenticatedUser,
)
from app.db.models import (
    ClinicalNoteRecord,
    EncounterRecord,
    FollowUpTaskRecord,
    LabReportRecord,
    PatientRecord,
)


def assigned_facility_ids(user: AuthenticatedUser, required_roles: set[str] | None = None) -> set[str]:
    """Return facilities where the user has one of the required roles.

    If no role set is supplied, return all assigned facilities. API endpoints
    handling protected resources should supply their operation's role set.
    """
    return {
        assignment.facility_id
        for assignment in user.assignments
        if required_roles is None or assignment.role in required_roles
    }


def require_assigned_facility(
    user: AuthenticatedUser,
    facility_id: str,
    required_roles: set[str],
) -> None:
    """Reject writes unless an allowed role is assigned in the target facility."""
    if facility_id not in assigned_facility_ids(user, required_roles):
        raise HTTPException(
            status_code=403,
            detail="You do not have the required role at the selected facility.",
        )


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=404, detail=detail)


def get_patient_in_scope(
    patient_id: str,
    db: Session,
    user: AuthenticatedUser,
    required_roles: set[str] = PATIENT_READ,
) -> PatientRecord:
    patient = db.get(PatientRecord, patient_id)
    if patient is None or patient.facility_id not in assigned_facility_ids(user, required_roles):
        raise _not_found("Patient not found")
    return patient


def get_encounter_in_scope(
    encounter_id: str,
    db: Session,
    user: AuthenticatedUser,
    required_roles: set[str] = CLINICAL_READ,
) -> EncounterRecord:
    encounter = db.get(EncounterRecord, encounter_id)
    if encounter is None or encounter.facility_id not in assigned_facility_ids(user, required_roles):
        raise _not_found("Encounter not found")
    patient = db.get(PatientRecord, encounter.patient_id)
    if patient is None or patient.facility_id != encounter.facility_id:
        raise _not_found("Encounter not found")
    return encounter


def get_note_in_scope(
    note_id: str,
    db: Session,
    user: AuthenticatedUser,
    required_roles: set[str] = CLINICAL_READ,
) -> ClinicalNoteRecord:
    note = db.get(ClinicalNoteRecord, note_id)
    if note is None:
        raise _not_found("Clinical note not found")
    get_encounter_in_scope(note.encounter_id, db, user, required_roles)
    return note


def get_lab_report_in_scope(
    report_id: str,
    db: Session,
    user: AuthenticatedUser,
    required_roles: set[str] = LAB_READ,
) -> LabReportRecord:
    statement = (
        select(LabReportRecord)
        .options(selectinload(LabReportRecord.observations))
        .where(LabReportRecord.report_id == report_id)
    )
    report = db.scalar(statement)
    if report is None:
        raise _not_found("Laboratory report not found")
    patient = get_patient_in_scope(report.patient_id, db, user, required_roles)
    if report.encounter_id is not None:
        encounter = get_encounter_in_scope(report.encounter_id, db, user, required_roles)
        if encounter.patient_id != patient.patient_id:
            raise _not_found("Laboratory report not found")
    return report


def get_followup_in_scope(
    task_id: str,
    db: Session,
    user: AuthenticatedUser,
    required_roles: set[str] = FOLLOW_UP_READ,
) -> FollowUpTaskRecord:
    task = db.get(FollowUpTaskRecord, task_id)
    if task is None:
        raise _not_found("Follow-up task not found")
    patient = get_patient_in_scope(task.patient_id, db, user, required_roles)
    if task.encounter_id is not None:
        encounter = get_encounter_in_scope(task.encounter_id, db, user, required_roles)
        if encounter.patient_id != patient.patient_id:
            raise _not_found("Follow-up task not found")
    if task.report_id is not None:
        report = get_lab_report_in_scope(task.report_id, db, user, required_roles)
        if report.patient_id != patient.patient_id:
            raise _not_found("Follow-up task not found")
    return task
