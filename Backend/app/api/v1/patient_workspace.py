"""Read-only patient workspace aggregate, scoped to one assigned facility."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth.dependencies import CLINICAL_READ, AuthenticatedUser, get_current_user
from app.auth.facility_scope import get_patient_in_scope
from app.db.models import (
    ClinicalNoteRecord,
    EncounterRecord,
    FollowUpTaskRecord,
    LabReportRecord,
)
from app.db.session import get_db
from app.models.patient_workspace import PatientWorkspace

router = APIRouter(prefix="/patients", tags=["Patient Workspace"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


@router.get(
    "/{patient_id}/workspace",
    response_model=PatientWorkspace,
    summary="Get a patient's consolidated workspace",
    description=(
        "Read-only view of one patient and their associated encounters, clinical notes, "
        "laboratory reports, and follow-up tasks. Requires a clinical-read role at the "
        "patient's facility. Synthetic development data only."
    ),
)
def get_patient_workspace(
    patient_id: str,
    db: DbSession,
    user: CurrentUser,
) -> dict[str, object]:
    """Build a consolidated workspace without crossing facility boundaries."""
    patient = get_patient_in_scope(patient_id, db, user, CLINICAL_READ)

    # Only encounters tied to both this patient and their facility are included.
    encounters = list(
        db.scalars(
            select(EncounterRecord)
            .where(
                EncounterRecord.patient_id == patient.patient_id,
                EncounterRecord.facility_id == patient.facility_id,
            )
            .order_by(EncounterRecord.started_at.desc(), EncounterRecord.encounter_id)
        ).all()
    )
    encounter_ids = {encounter.encounter_id for encounter in encounters}

    # Clinical notes are reached through the scoped encounters, never directly by ID.
    clinical_notes = []
    if encounter_ids:
        clinical_notes = list(
            db.scalars(
                select(ClinicalNoteRecord)
                .where(ClinicalNoteRecord.encounter_id.in_(encounter_ids))
                .order_by(ClinicalNoteRecord.created_at.desc(), ClinicalNoteRecord.version.desc())
            ).all()
        )

    # A report with a mismatched encounter link is excluded rather than exposed.
    candidate_reports = list(
        db.scalars(
            select(LabReportRecord)
            .options(selectinload(LabReportRecord.observations))
            .where(LabReportRecord.patient_id == patient.patient_id)
            .order_by(LabReportRecord.received_at.desc(), LabReportRecord.report_id)
        ).all()
    )
    lab_reports = [
        report for report in candidate_reports
        if report.encounter_id is None or report.encounter_id in encounter_ids
    ]
    report_ids = {report.report_id for report in lab_reports}

    # Follow-ups must belong to this patient and any optional linked records must
    # themselves be present in the scoped workspace.
    candidate_tasks = list(
        db.scalars(
            select(FollowUpTaskRecord)
            .where(FollowUpTaskRecord.patient_id == patient.patient_id)
            .order_by(FollowUpTaskRecord.created_at.desc(), FollowUpTaskRecord.task_id)
        ).all()
    )
    follow_up_tasks = [
        task for task in candidate_tasks
        if (task.encounter_id is None or task.encounter_id in encounter_ids)
        and (task.report_id is None or task.report_id in report_ids)
    ]

    return {
        "patient": patient,
        "encounters": encounters,
        "clinical_notes": clinical_notes,
        "lab_reports": lab_reports,
        "follow_up_tasks": follow_up_tasks,
    }
