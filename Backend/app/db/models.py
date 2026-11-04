"""Database models. Use synthetic data only during development."""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Float,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    """Return the current UTC time for audit-friendly timestamps."""
    return datetime.now(timezone.utc)


class PatientRecord(Base):
    """Persisted patient-directory fields for the prototype."""

    __tablename__ = "patients"
    __table_args__ = (
        CheckConstraint(
            "record_status IN ('active', 'inactive')",
            name="ck_patients_record_status",
        ),
    )

    patient_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    date_of_birth: Mapped[Date | None] = mapped_column(Date, nullable=True)
    record_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    facility_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)


class EncounterRecord(Base):
    """A synthetic clinical encounter linked to one patient."""

    __tablename__ = "encounters"
    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress', 'completed', 'cancelled')",
            name="ck_encounters_status",
        ),
    )

    encounter_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("patients.patient_id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    clinician_name: Mapped[str] = mapped_column(String(200), nullable=False)
    encounter_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="consultation", server_default="consultation"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="in_progress", server_default="in_progress"
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class ClinicalNoteRecord(Base):
    """Versioned clinical note content with an explicit human-review state."""

    __tablename__ = "clinical_notes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'awaiting_review', 'approved')",
            name="ck_clinical_notes_status",
        ),
        UniqueConstraint("encounter_id", "version", name="uq_clinical_notes_encounter_version"),
    )

    note_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    encounter_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("encounters.encounter_id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    author_name: Mapped[str] = mapped_column(String(200), nullable=False)
    presenting_complaint: Mapped[str | None] = mapped_column(Text, nullable=True)
    history_of_present_illness: Mapped[str | None] = mapped_column(Text, nullable=True)
    relevant_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    medications_and_allergies: Mapped[str | None] = mapped_column(Text, nullable=True)
    vitals: Mapped[str | None] = mapped_column(Text, nullable=True)
    examination: Mapped[str | None] = mapped_column(Text, nullable=True)
    assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft", server_default="draft"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)


class LabReportRecord(Base):
    """A laboratory report and its review lifecycle for synthetic records."""

    __tablename__ = "lab_reports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('received', 'validated', 'awaiting_review', 'reviewed', 'follow_up_required', 'closed')",
            name="ck_lab_reports_status",
        ),
    )

    report_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("patients.patient_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    encounter_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("encounters.encounter_id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source_system: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="received", server_default="received", index=True
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    observations: Mapped[list["LabObservationRecord"]] = relationship(
        back_populates="report", cascade="all, delete-orphan", order_by="LabObservationRecord.test_code"
    )


class LabObservationRecord(Base):
    """One result value belonging to a laboratory report."""

    __tablename__ = "lab_observations"
    __table_args__ = (
        CheckConstraint(
            "value_numeric IS NOT NULL OR value_text IS NOT NULL",
            name="ck_lab_observations_has_value",
        ),
    )

    observation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    report_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lab_reports.report_id", ondelete="CASCADE"), nullable=False, index=True
    )
    test_code: Mapped[str] = mapped_column(String(64), nullable=False)
    test_name: Mapped[str] = mapped_column(String(160), nullable=False)
    value_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference_range: Mapped[str | None] = mapped_column(String(200), nullable=True)
    interpretation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    report: Mapped["LabReportRecord"] = relationship(back_populates="observations")


class FollowUpTaskRecord(Base):
    """A traceable follow-up task linked to a patient and optionally a result/encounter."""

    __tablename__ = "follow_up_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'assigned', 'in_progress', 'completed', 'escalated', 'cancelled')",
            name="ck_follow_up_tasks_status",
        ),
    )

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("patients.patient_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    report_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("lab_reports.report_id", ondelete="RESTRICT"), nullable=True, index=True
    )
    encounter_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("encounters.encounter_id", ondelete="RESTRICT"), nullable=True, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="open", server_default="open", index=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEventRecord(Base):
    """Development audit record for successful database mutations.

    Authenticated API mutations use the actor ID attached to the request session.
    Unauthenticated seed/setup work can still use a development placeholder. This
    is not a production security audit trail.
    """

    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str] = mapped_column(
        String(100), nullable=False, default="DEVELOPMENT-MODE-UNVERIFIED"
    )
    actor_source: Mapped[str] = mapped_column(
        String(40), nullable=False, default="development-placeholder"
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    outcome: Mapped[str] = mapped_column(
        String(20), nullable=False, default="success", server_default="success"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )


class UserRecord(Base):
    """Locally provisioned development user; password is stored as a hash."""

    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class UserFacilityRoleRecord(Base):
    """Assign a role to a user within a facility context."""

    __tablename__ = "user_facility_roles"
    __table_args__ = (
        CheckConstraint(
            "role IN ('receptionist', 'nurse', 'clinician', 'laboratory_worker', "
            "'follow_up_worker', 'facility_admin', 'auditor', 'platform_admin')",
            name="ck_user_facility_roles_role",
        ),
        UniqueConstraint("user_id", "facility_id", "role", name="uq_user_facility_roles_assignment"),
    )

    assignment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class FacilityRecord(Base):
    """Managed facility directory entry. Facility identifiers remain stable."""

    __tablename__ = "facilities"

    facility_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    district: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class NotificationRecord(Base):
    """User-specific operational notification; message content must not contain clinical details."""

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "category IN ('workflow', 'laboratory', 'follow_up', 'administration', 'system')",
            name="ck_notifications_category",
        ),
        Index(
            "ix_notifications_recipient_created",
            "recipient_user_id",
            "created_at",
        ),
    )

    notification_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    recipient_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("facilities.facility_id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    message: Mapped[str] = mapped_column(String(800), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClaimDocumentRecord(Base):
    """A locally stored invoice PDF and its extracted, reviewable claim fields."""

    __tablename__ = "claim_documents"
    __table_args__ = (
        CheckConstraint(
            "extraction_status IN ('extracted', 'needs_ocr', 'failed', 'duplicate')",
            name="ck_claim_documents_extraction_status",
        ),
        CheckConstraint(
            "claim_status IN ('needs_review', 'ready_for_approval', 'approved', 'batched', 'submitted_externally', 'duplicate')",
            name="ck_claim_documents_claim_status",
        ),
    )

    claim_document_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    facility_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("facilities.facility_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    uploaded_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    membership_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    service_date: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    patient_first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tariff_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(precision=12,scale=2), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extraction_status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    claim_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    extracted_fields_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    validation_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    batch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("claim_batches.batch_id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ClaimBatchRecord(Base):
    """A group of approved invoice documents prepared for an external submission workflow."""

    __tablename__ = "claim_batches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('prepared', 'exported', 'submitted_externally', 'acknowledged', 'rejected')",
            name="ck_claim_batches_status",
        ),
    )

    batch_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_number: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    facility_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("facilities.facility_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="prepared", index=True)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False, default=Decimal("0.00"))
    external_submission_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    external_submission_channel: Mapped[str | None] = mapped_column(String(80), nullable=True)
    external_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledgement_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
