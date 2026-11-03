"""Pydantic schemas for clinical encounter API requests and responses."""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EncounterStatus(str, Enum):
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class EncounterCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(min_length=1, max_length=40, examples=["DEMO-0001"])
    facility_id: str = Field(min_length=1, max_length=80, examples=["DEMO-FACILITY-001"])
    clinician_name: str = Field(min_length=1, max_length=200, examples=["Demo Clinician"])
    encounter_type: str = Field(default="consultation", min_length=1, max_length=100)

    @field_validator("patient_id", "facility_id", "clinician_name", "encounter_type")
    @classmethod
    def strip_and_reject_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field cannot be blank.")
        return cleaned


class EncounterStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: EncounterStatus


class Encounter(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    encounter_id: str
    patient_id: str
    facility_id: str
    clinician_name: str
    encounter_type: str
    status: EncounterStatus
    started_at: datetime
    updated_at: datetime
