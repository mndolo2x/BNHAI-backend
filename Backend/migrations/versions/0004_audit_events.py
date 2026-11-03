"""Create development audit events table.

Revision ID: 0004_audit_events
Revises: 0003_labs_followups
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_audit_events"
down_revision = "0003_labs_followups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column(
            "actor_id", sa.String(length=100), nullable=False,
            server_default="DEVELOPMENT-MODE-UNVERIFIED",
        ),
        sa.Column(
            "actor_source", sa.String(length=40), nullable=False,
            server_default="development-placeholder",
        ),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.String(length=200), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False, server_default="success"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_audit_events_action", "audit_events", ["action"], unique=False)
    op.create_index("ix_audit_events_resource_type", "audit_events", ["resource_type"], unique=False)
    op.create_index("ix_audit_events_resource_id", "audit_events", ["resource_id"], unique=False)
    op.create_index("ix_audit_events_occurred_at", "audit_events", ["occurred_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_events_occurred_at", table_name="audit_events")
    op.drop_index("ix_audit_events_resource_id", table_name="audit_events")
    op.drop_index("ix_audit_events_resource_type", table_name="audit_events")
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_table("audit_events")
