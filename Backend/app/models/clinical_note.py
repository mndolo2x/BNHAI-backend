"""Pydantic schemas for versioned clinical notes and review actions."""
from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

NoteText = Annotated[str | None, Field(max_length=10000)]


class NoteStatus(str, Enum):
    draft = "draft"
    awaiting_review = "awaiting_review"
    approved = "approved"


class ClinicalNoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author_name: str = Field(min_length=1, max_length=200, examples=["Demo Clinician"])
    presenting_complaint: NoteText = None
    history_of_present_illness: NoteText = None
    relevant_history: NoteText = None
    medications_and_allergies: NoteText = None
    vitals: NoteText = None
    examination: NoteText = None
    assessment: NoteText = None
    plan: NoteText = None
    follow_up: NoteText = None

    @field_validator("author_name")
    @classmethod
    def author_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Author name cannot be blank.")
        return cleaned

    @field_validator(
        "presenting_complaint", "history_of_present_illness", "relevant_history",
        "medications_and_allergies", "vitals", "examination", "assessment", "plan", "follow_up"
    )
    @classmethod
    def trim_note_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class ClinicalNoteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author_name: str | None = Field(default=None, min_length=1, max_length=200)
    presenting_complaint: NoteText = None
    history_of_present_illness: NoteText = None
    relevant_history: NoteText = None
    medications_and_allergies: NoteText = None
    vitals: NoteText = None
    examination: NoteText = None
    assessment: NoteText = None
    plan: NoteText = None
    follow_up: NoteText = None

    @field_validator("author_name")
    @classmethod
    def clean_author_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Author name cannot be null.")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Author name cannot be blank.")
        return cleaned

    @field_validator(
        "presenting_complaint", "history_of_present_illness", "relevant_history",
        "medications_and_allergies", "vitals", "examination", "assessment", "plan", "follow_up"
    )
    @classmethod
    def trim_note_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class NoteApprove(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewer_name: str = Field(min_length=1, max_length=200, examples=["Demo Reviewer"])

    @field_validator("reviewer_name")
    @classmethod
    def reviewer_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Reviewer name cannot be blank.")
        return cleaned


class ClinicalNote(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    note_id: str
    encounter_id: str
    version: int
    author_name: str
    presenting_complaint: str | None
    history_of_present_illness: str | None
    relevant_history: str | None
    medications_and_allergies: str | None
    vitals: str | None
    examination: str | None
    assessment: str | None
    plan: str | None
    follow_up: str | None
    status: NoteStatus
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    approved_at: datetime | None
    approved_by: str | None
