"""Combined read-only response for a patient workspace."""

from pydantic import BaseModel, ConfigDict

from app.models.clinical_note import ClinicalNote
from app.models.encounter import Encounter
from app.models.followup import FollowUpTask
from app.models.lab_result import LabReport
from app.models.patient import Patient


class PatientWorkspace(BaseModel):
    """Patient and related records visible within the user's facility scope."""

    model_config = ConfigDict(extra="forbid")

    patient: Patient
    encounters: list[Encounter]
    clinical_notes: list[ClinicalNote]
    lab_reports: list[LabReport]
    follow_up_tasks: list[FollowUpTask]
