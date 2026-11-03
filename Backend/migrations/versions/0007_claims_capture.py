"""Add local invoice capture and claim-batch preparation.

Revision ID: 0007_claims_capture
Revises: 0006_operational
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_claims_capture"
down_revision = "0006_operational"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "claim_batches",
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("batch_number", sa.String(length=80), nullable=False),
        sa.Column("facility_id", sa.String(length=80), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("document_count", sa.Integer(), nullable=False),
        sa.Column("total_amount", sa.Float(), nullable=False),
        sa.Column("external_submission_reference", sa.String(length=200), nullable=True),
        sa.Column("external_submission_channel", sa.String(length=80), nullable=True),
        sa.Column("external_submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledgement_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('prepared', 'exported', 'submitted_externally', 'acknowledged', 'rejected')",
            name="ck_claim_batches_status",
        ),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.facility_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.user_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("batch_id"),
    )
    op.create_index("ix_claim_batches_batch_number", "claim_batches", ["batch_number"], unique=True)
    op.create_index("ix_claim_batches_facility_id", "claim_batches", ["facility_id"], unique=False)
    op.create_index("ix_claim_batches_status", "claim_batches", ["status"], unique=False)

    op.create_table(
        "claim_documents",
        sa.Column("claim_document_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=80), nullable=False),
        sa.Column("uploaded_by", sa.String(length=36), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("invoice_number", sa.String(length=100), nullable=True),
        sa.Column("membership_number", sa.String(length=100), nullable=True),
        sa.Column("service_date", sa.String(length=10), nullable=True),
        sa.Column("patient_first_name", sa.String(length=120), nullable=True),
        sa.Column("tariff_code", sa.String(length=80), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("extraction_status", sa.String(length=30), nullable=False),
        sa.Column("claim_status", sa.String(length=40), nullable=False),
        sa.Column("extracted_fields_json", sa.Text(), nullable=False),
        sa.Column("validation_json", sa.Text(), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "extraction_status IN ('extracted', 'needs_ocr', 'failed', 'duplicate')",
            name="ck_claim_documents_extraction_status",
        ),
        sa.CheckConstraint(
            "claim_status IN ('needs_review', 'ready_for_approval', 'approved', 'batched', 'submitted_externally', 'duplicate')",
            name="ck_claim_documents_claim_status",
        ),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.facility_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.user_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["batch_id"], ["claim_batches.batch_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("claim_document_id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_claim_documents_facility_id", "claim_documents", ["facility_id"], unique=False)
    op.create_index("ix_claim_documents_uploaded_by", "claim_documents", ["uploaded_by"], unique=False)
    op.create_index("ix_claim_documents_sha256", "claim_documents", ["sha256"], unique=False)
    op.create_index("ix_claim_documents_invoice_number", "claim_documents", ["invoice_number"], unique=False)
    op.create_index("ix_claim_documents_membership_number", "claim_documents", ["membership_number"], unique=False)
    op.create_index("ix_claim_documents_service_date", "claim_documents", ["service_date"], unique=False)
    op.create_index("ix_claim_documents_extraction_status", "claim_documents", ["extraction_status"], unique=False)
    op.create_index("ix_claim_documents_claim_status", "claim_documents", ["claim_status"], unique=False)
    op.create_index("ix_claim_documents_batch_id", "claim_documents", ["batch_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_claim_documents_batch_id", table_name="claim_documents")
    op.drop_index("ix_claim_documents_claim_status", table_name="claim_documents")
    op.drop_index("ix_claim_documents_extraction_status", table_name="claim_documents")
    op.drop_index("ix_claim_documents_service_date", table_name="claim_documents")
    op.drop_index("ix_claim_documents_membership_number", table_name="claim_documents")
    op.drop_index("ix_claim_documents_invoice_number", table_name="claim_documents")
    op.drop_index("ix_claim_documents_sha256", table_name="claim_documents")
    op.drop_index("ix_claim_documents_uploaded_by", table_name="claim_documents")
    op.drop_index("ix_claim_documents_facility_id", table_name="claim_documents")
    op.drop_table("claim_documents")
    op.drop_index("ix_claim_batches_status", table_name="claim_batches")
    op.drop_index("ix_claim_batches_facility_id", table_name="claim_batches")
    op.drop_index("ix_claim_batches_batch_number", table_name="claim_batches")
    op.drop_table("claim_batches")
