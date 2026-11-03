"""Add facility directory and user notifications.

Revision ID: 0006_operational
Revises: 0005_users_roles
"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "0006_operational"
down_revision = "0005_users_roles"
branch_labels = None
depends_on = None


def _display_name(facility_id: str) -> str:
    if facility_id.startswith("DEMO-FACILITY-"):
        suffix = facility_id.removeprefix("DEMO-FACILITY-")
        return f"Demo Facility {suffix}"
    return facility_id.replace("-", " ").replace("_", " ").title()


def upgrade() -> None:
    op.create_table(
        "facilities",
        sa.Column("facility_id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("district", sa.String(length=120), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("contact_email", sa.String(length=254), nullable=True),
        sa.Column("contact_phone", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("facility_id"),
    )
    op.create_index("ix_facilities_name", "facilities", ["name"], unique=False)

    bind = op.get_bind()
    existing_ids = bind.execute(
        sa.text(
            "SELECT facility_id FROM patients "
            "UNION SELECT facility_id FROM encounters "
            "UNION SELECT facility_id FROM user_facility_roles"
        )
    ).scalars().all()
    now = datetime.now(timezone.utc)
    for facility_id in sorted(set(existing_ids)):
        bind.execute(
            sa.text(
                "INSERT INTO facilities "
                "(facility_id, name, created_at, updated_at) "
                "VALUES (:facility_id, :name, :created_at, :updated_at)"
            ),
            {
                "facility_id": facility_id,
                "name": _display_name(facility_id),
                "created_at": now,
                "updated_at": now,
            },
        )

    op.create_table(
        "notifications",
        sa.Column("notification_id", sa.String(length=36), nullable=False),
        sa.Column("recipient_user_id", sa.String(length=36), nullable=False),
        sa.Column("facility_id", sa.String(length=80), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("message", sa.String(length=800), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=True),
        sa.Column("resource_id", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "category IN ('workflow', 'laboratory', 'follow_up', 'administration', 'system')",
            name="ck_notifications_category",
        ),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.facility_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("notification_id"),
    )
    op.create_index("ix_notifications_recipient_user_id", "notifications", ["recipient_user_id"], unique=False)
    op.create_index("ix_notifications_facility_id", "notifications", ["facility_id"], unique=False)
    op.create_index("ix_notifications_category", "notifications", ["category"], unique=False)
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"], unique=False)
    op.create_index(
        "ix_notifications_recipient_created",
        "notifications",
        ["recipient_user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_recipient_created", table_name="notifications")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_category", table_name="notifications")
    op.drop_index("ix_notifications_facility_id", table_name="notifications")
    op.drop_index("ix_notifications_recipient_user_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_facilities_name", table_name="facilities")
    op.drop_table("facilities")
