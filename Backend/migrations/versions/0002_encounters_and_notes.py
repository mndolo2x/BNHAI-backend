"""Create encounter and clinical-note tables.

Revision ID: 0002_enc_notes
Revises: 0001_patients
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_enc_notes"
down_revision = "0001_patients"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "encounters",
        sa.Column("encounter_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=40), nullable=False),
        sa.Column("facility_id", sa.String(length=80), nullable=False),
        sa.Column("clinician_name", sa.String(length=200), nullable=False),
        sa.Column("encounter_type", sa.String(length=100), server_default="consultation", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="in_progress", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('in_progress', 'completed', 'cancelled')",
            name="ck_encounters_status",
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.patient_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("encounter_id"),
    )
    op.create_index("ix_encounters_patient_id", "encounters", ["patient_id"], unique=False)
    op.create_index("ix_encounters_facility_id", "encounters", ["facility_id"], unique=False)

    op.create_table(
        "clinical_notes",
        sa.Column("note_id", sa.String(length=36), nullable=False),
        sa.Column("encounter_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("author_name", sa.String(length=200), nullable=False),
        sa.Column("presenting_complaint", sa.Text(), nullable=True),
        sa.Column("history_of_present_illness", sa.Text(), nullable=True),
        sa.Column("relevant_history", sa.Text(), nullable=True),
        sa.Column("medications_and_allergies", sa.Text(), nullable=True),
        sa.Column("vitals", sa.Text(), nullable=True),
        sa.Column("examination", sa.Text(), nullable=True),
        sa.Column("assessment", sa.Text(), nullable=True),
        sa.Column("plan", sa.Text(), nullable=True),
        sa.Column("follow_up", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="draft", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(length=200), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'awaiting_review', 'approved')",
            name="ck_clinical_notes_status",
        ),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.encounter_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("note_id"),
        sa.UniqueConstraint("encounter_id", "version", name="uq_clinical_notes_encounter_version"),
    )
    op.create_index("ix_clinical_notes_encounter_id", "clinical_notes", ["encounter_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_clinical_notes_encounter_id", table_name="clinical_notes")
    op.drop_table("clinical_notes")
    op.drop_index("ix_encounters_facility_id", table_name="encounters")
    op.drop_index("ix_encounters_patient_id", table_name="encounters")
    op.drop_table("encounters")
