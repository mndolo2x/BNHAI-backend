"""Create laboratory report, observation, and follow-up task tables.

Revision ID: 0003_labs_followups
Revises: 0002_enc_notes
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_labs_followups"
down_revision = "0002_enc_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lab_reports",
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=40), nullable=False),
        sa.Column("encounter_id", sa.String(length=36), nullable=True),
        sa.Column("source_system", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="received", nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('received', 'validated', 'awaiting_review', 'reviewed', 'follow_up_required', 'closed')",
            name="ck_lab_reports_status",
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.patient_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.encounter_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("report_id"),
    )
    op.create_index("ix_lab_reports_patient_id", "lab_reports", ["patient_id"], unique=False)
    op.create_index("ix_lab_reports_encounter_id", "lab_reports", ["encounter_id"], unique=False)
    op.create_index("ix_lab_reports_status", "lab_reports", ["status"], unique=False)

    op.create_table(
        "lab_observations",
        sa.Column("observation_id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("test_code", sa.String(length=64), nullable=False),
        sa.Column("test_name", sa.String(length=160), nullable=False),
        sa.Column("value_numeric", sa.Float(), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("reference_range", sa.String(length=200), nullable=True),
        sa.Column("interpretation", sa.String(length=200), nullable=True),
        sa.CheckConstraint(
            "value_numeric IS NOT NULL OR value_text IS NOT NULL",
            name="ck_lab_observations_has_value",
        ),
        sa.ForeignKeyConstraint(["report_id"], ["lab_reports.report_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("observation_id"),
    )
    op.create_index("ix_lab_observations_report_id", "lab_observations", ["report_id"], unique=False)

    op.create_table(
        "follow_up_tasks",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=40), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=True),
        sa.Column("encounter_id", sa.String(length=36), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("assigned_to", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="open", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('open', 'assigned', 'in_progress', 'completed', 'escalated', 'cancelled')",
            name="ck_follow_up_tasks_status",
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.patient_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["report_id"], ["lab_reports.report_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.encounter_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("task_id"),
    )
    op.create_index("ix_follow_up_tasks_patient_id", "follow_up_tasks", ["patient_id"], unique=False)
    op.create_index("ix_follow_up_tasks_report_id", "follow_up_tasks", ["report_id"], unique=False)
    op.create_index("ix_follow_up_tasks_encounter_id", "follow_up_tasks", ["encounter_id"], unique=False)
    op.create_index("ix_follow_up_tasks_assigned_to", "follow_up_tasks", ["assigned_to"], unique=False)
    op.create_index("ix_follow_up_tasks_status", "follow_up_tasks", ["status"], unique=False)
    op.create_index("ix_follow_up_tasks_due_at", "follow_up_tasks", ["due_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_follow_up_tasks_due_at", table_name="follow_up_tasks")
    op.drop_index("ix_follow_up_tasks_status", table_name="follow_up_tasks")
    op.drop_index("ix_follow_up_tasks_assigned_to", table_name="follow_up_tasks")
    op.drop_index("ix_follow_up_tasks_encounter_id", table_name="follow_up_tasks")
    op.drop_index("ix_follow_up_tasks_report_id", table_name="follow_up_tasks")
    op.drop_index("ix_follow_up_tasks_patient_id", table_name="follow_up_tasks")
    op.drop_table("follow_up_tasks")
    op.drop_index("ix_lab_observations_report_id", table_name="lab_observations")
    op.drop_table("lab_observations")
    op.drop_index("ix_lab_reports_status", table_name="lab_reports")
    op.drop_index("ix_lab_reports_encounter_id", table_name="lab_reports")
    op.drop_index("ix_lab_reports_patient_id", table_name="lab_reports")
    op.drop_table("lab_reports")
