"""Pydantic request and response models for patient API payloads."""
from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PatientStatus(str, Enum):
    """Administrative record status; not a clinical condition."""

    active = "active"
    inactive = "inactive"


class Patient(BaseModel):
    """Patient response model returned by the API."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    patient_id: str = Field(min_length=1, max_length=40, examples=["DEMO-0001"])
    display_name: str = Field(min_length=1, max_length=200, examples=["Demo Patient A"])
    date_of_birth: date | None = None
    record_status: PatientStatus = PatientStatus.active
    facility_id: str = Field(min_length=1, max_length=80, examples=["DEMO-FACILITY-001"])


class PatientCreate(BaseModel):
    """Allowed fields for creating a synthetic patient record."""

    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(min_length=1, max_length=40, examples=["DEMO-0004"])
    display_name: str = Field(min_length=1, max_length=200, examples=["Demo Patient D"])
    date_of_birth: date | None = None
    record_status: PatientStatus = PatientStatus.active
    facility_id: str = Field(min_length=1, max_length=80, examples=["DEMO-FACILITY-001"])

    @field_validator("patient_id", "display_name", "facility_id")
    @classmethod
    def strip_and_reject_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field cannot be blank.")
        return cleaned
