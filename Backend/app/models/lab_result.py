"""Pydantic schemas for synthetic laboratory reports and observations."""
from datetime import datetime
from enum import Enum
import math

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LabReportStatus(str, Enum):
    received = "received"
    validated = "validated"
    awaiting_review = "awaiting_review"
    reviewed = "reviewed"
    follow_up_required = "follow_up_required"
    closed = "closed"




class LabObservationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_code: str = Field(min_length=1, max_length=64, examples=["HB"])
    test_name: str = Field(min_length=1, max_length=160, examples=["Haemoglobin"])
    value_numeric: float | None = None
    value_text: str | None = Field(default=None, max_length=2000)
    unit: str | None = Field(default=None, max_length=64)
    reference_range: str | None = Field(default=None, max_length=200)
    interpretation: str | None = Field(default=None, max_length=200)

    @field_validator("test_code", "test_name")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field cannot be blank.")
        return cleaned

    @field_validator("value_text", "unit", "reference_range", "interpretation")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("value_numeric")
    @classmethod
    def numeric_result_must_be_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("Numeric result must be finite.")
        return value

    @model_validator(mode="after")
    def require_one_result_value(self):
        if self.value_numeric is None and self.value_text is None:
            raise ValueError("Provide either value_numeric or value_text.")
        if self.value_numeric is not None and self.value_text is not None:
            raise ValueError("Provide only one of value_numeric or value_text.")
        return self


class LabObservation(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    observation_id: str
    report_id: str
    test_code: str
    test_name: str
    value_numeric: float | None
    value_text: str | None
    unit: str | None
    reference_range: str | None
    interpretation: str | None


class LabReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(min_length=1, max_length=40, examples=["DEMO-0001"])
    encounter_id: str | None = Field(default=None, min_length=1, max_length=36)
    source_system: str = Field(min_length=1, max_length=120, examples=["DEMO-LIS"])
    issued_at: datetime | None = None
    observations: list[LabObservationCreate] = Field(min_length=1, max_length=100)

    @field_validator("patient_id", "source_system")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field cannot be blank.")
        return cleaned

    @field_validator("encounter_id")
    @classmethod
    def trim_optional_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Encounter ID cannot be blank when provided.")
        return cleaned


class LabReportStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: LabReportStatus


class LabReport(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    report_id: str
    patient_id: str
    encounter_id: str | None
    source_system: str
    status: LabReportStatus
    issued_at: datetime | None
    received_at: datetime
    updated_at: datetime
    observations: list[LabObservation]
