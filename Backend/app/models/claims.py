"""Schemas for invoice capture, review, and internally prepared claim batches."""
from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ClaimExtractedFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_number: str | None = Field(default=None, max_length=100)
    member_surname_initials: str | None = Field(default=None, max_length=200)
    patient_first_name: str | None = Field(default=None, max_length=120)
    benefit_option: str | None = Field(default=None, max_length=120)
    membership_number: str | None = Field(default=None, max_length=100)
    practice_code: str | None = Field(default=None, max_length=100)
    practice_name: str | None = Field(default=None, max_length=200)
    provider_name: str | None = Field(default=None, max_length=200)
    service_date: date | None = None
    service_description: str | None = Field(default=None, max_length=1000)
    diagnosis_code: str | None = Field(default=None, max_length=40)
    tariff_code: str | None = Field(default=None, max_length=80)
    quantity: float | None = Field(default=None, gt=0, le=10000)
    amount: float | None = Field(default=None, ge=0, le=100000000)
    currency: str = Field(default="BWP", min_length=3, max_length=3)
    member_signature_confirmed: bool | None = None
    provider_signature_confirmed: bool | None = None
    referral_document_confirmed: bool | None = None

    @field_validator(
        "invoice_number", "member_surname_initials", "patient_first_name", "benefit_option",
        "membership_number", "practice_code", "practice_name", "provider_name", "service_description",
        "diagnosis_code", "tariff_code", "currency",
    )
    @classmethod
    def trim_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ClaimValidation(BaseModel):
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    can_approve: bool = False
    validation_scope: str = "Basic completeness checks only; not a BPOMAS adjudication decision."


class ClaimDocumentRead(BaseModel):
    claim_document_id: str
    facility_id: str
    original_filename: str
    sha256: str
    file_size_bytes: int
    page_count: int | None
    extraction_status: str
    claim_status: str
    extracted_fields: ClaimExtractedFields
    validation: ClaimValidation
    batch_id: str | None
    created_at: datetime
    updated_at: datetime
    duplicate_of: str | None = None


class ClaimUploadFailure(BaseModel):
    filename: str
    error: str


class ClaimUploadResult(BaseModel):
    uploaded: list[ClaimDocumentRead]
    rejected: list[ClaimUploadFailure]
    received_count: int


class ClaimDocumentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: ClaimExtractedFields


class ClaimApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    member_signature_confirmed: bool
    provider_signature_confirmed: bool | None = None
    referral_document_confirmed: bool | None = None


class ClaimBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facility_id: str = Field(min_length=2, max_length=80)
    claim_document_ids: list[str] = Field(min_length=1, max_length=200)

    @field_validator("claim_document_ids")
    @classmethod
    def unique_document_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("A claim document may only appear once in a batch.")
        return value


class ClaimBatchRead(BaseModel):
    batch_id: str
    batch_number: str
    facility_id: str
    status: str
    document_count: int
    total_amount: float
    external_submission_reference: str | None
    external_submission_channel: str | None
    external_submitted_at: datetime | None
    acknowledgement_notes: str | None
    created_at: datetime
    updated_at: datetime


class ClaimBatchExternalSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_submission_reference: str = Field(min_length=2, max_length=200)
    external_submission_channel: str = Field(min_length=2, max_length=80)
    acknowledgement_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("external_submission_reference", "external_submission_channel", "acknowledgement_notes")
    @classmethod
    def trim_values(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ClaimBatchAcknowledgement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal["accepted", "rejected"]
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("notes")
    @classmethod
    def trim_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None
