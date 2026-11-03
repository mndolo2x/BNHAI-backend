"""Pydantic schemas for workflow follow-up tasks."""
from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FollowUpStatus(str, Enum):
    open = "open"
    assigned = "assigned"
    in_progress = "in_progress"
    completed = "completed"
    escalated = "escalated"
    cancelled = "cancelled"


class FollowUpCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(min_length=1, max_length=40, examples=["DEMO-0001"])
    report_id: str | None = Field(default=None, min_length=1, max_length=36)
    encounter_id: str | None = Field(default=None, min_length=1, max_length=36)
    description: str = Field(min_length=1, max_length=2000)
    assigned_to: str | None = Field(default=None, max_length=200)
    due_at: datetime | None = None

    @field_validator("patient_id", "description")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field cannot be blank.")
        return cleaned

    @field_validator("report_id", "encounter_id")
    @classmethod
    def trim_optional_ids(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("An ID cannot be blank when provided.")
        return cleaned

    @field_validator("assigned_to")
    @classmethod
    def clean_assignee(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        return cleaned


class FollowUpUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assigned_to: str | None = Field(default=None, max_length=200)
    due_at: datetime | None = None
    status: FollowUpStatus | None = None
    outcome: Annotated[str | None, Field(max_length=4000)] = None

    @field_validator("assigned_to")
    @classmethod
    def clean_assignee(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("outcome")
    @classmethod
    def clean_outcome(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class FollowUpTask(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    task_id: str
    patient_id: str
    report_id: str | None
    encounter_id: str | None
    description: str
    assigned_to: str | None
    status: FollowUpStatus
    due_at: datetime | None
    outcome: str | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
