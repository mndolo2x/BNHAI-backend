"""Add local users and facility role assignments.

Revision ID: 0005_users_roles
Revises: 0004_audit_events
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_users_roles"
down_revision = "0004_audit_events"
branch_labels = None
depends_on = None


VALID_ROLES = (
    "receptionist", "nurse", "clinician", "laboratory_worker",
    "follow_up_worker", "facility_admin", "auditor", "platform_admin",
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "user_facility_roles",
        sa.Column("assignment_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=80), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('receptionist', 'nurse', 'clinician', 'laboratory_worker', "
            "'follow_up_worker', 'facility_admin', 'auditor', 'platform_admin')",
            name="ck_user_facility_roles_role",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("assignment_id"),
        sa.UniqueConstraint("user_id", "facility_id", "role", name="uq_user_facility_roles_assignment"),
    )
    op.create_index("ix_user_facility_roles_user_id", "user_facility_roles", ["user_id"], unique=False)
    op.create_index("ix_user_facility_roles_facility_id", "user_facility_roles", ["facility_id"], unique=False)
    op.create_index("ix_user_facility_roles_role", "user_facility_roles", ["role"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_facility_roles_role", table_name="user_facility_roles")
    op.drop_index("ix_user_facility_roles_facility_id", table_name="user_facility_roles")
    op.drop_index("ix_user_facility_roles_user_id", table_name="user_facility_roles")
    op.drop_table("user_facility_roles")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
