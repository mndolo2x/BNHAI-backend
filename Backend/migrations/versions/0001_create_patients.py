"""Create the patients table.

Revision ID: 0001_patients
Revises:
Create Date: 2026-10-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_patients"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patients",
        sa.Column("patient_id", sa.String(length=40), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("record_status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("facility_id", sa.String(length=80), nullable=False),
        sa.CheckConstraint(
            "record_status IN ('active', 'inactive')",
            name="ck_patients_record_status",
        ),
        sa.PrimaryKeyConstraint("patient_id"),
    )
    op.create_index("ix_patients_display_name", "patients", ["display_name"], unique=False)
    op.create_index("ix_patients_facility_id", "patients", ["facility_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_patients_facility_id", table_name="patients")
    op.drop_index("ix_patients_display_name", table_name="patients")
    op.drop_table("patients")
