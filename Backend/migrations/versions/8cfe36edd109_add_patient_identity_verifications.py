"""add patient identity verifications

Revision ID: 8cfe36edd109
Revises: 223a9308a38e
Create Date: 2026-11-09 14:56:14.120930
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '8cfe36edd109'
down_revision: Union[str, None] = '223a9308a38e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    op.create_table(
        "patient_identity_verifications",
        sa.Column("verification_id", sa.String(36), primary_key=True),
        sa.Column("link_id", sa.String(36), nullable=False),
        sa.Column("verification_method", sa.String(40), nullable=False),
        sa.Column("verified_by", sa.String(36), nullable=False),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "verification_reference",
            sa.String(100),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "verification_method IN "
            "('in_person_document_check', "
            "'approved_remote_verification')",
            name="ck_patient_identity_verification_method",
        ),
        sa.ForeignKeyConstraint(
            ["link_id"],
            ["patient_account_links.link_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["verified_by"],
            ["users.user_id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "link_id",
            name="uq_patient_identity_verification_link",
        ),
    )

    op.create_index(
        "ix_patient_identity_verifications_link_id",
        "patient_identity_verifications",
        ["link_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_patient_identity_verifications_link_id",
        table_name="patient_identity_verifications",
    )

    op.drop_table("patient_identity_verifications")
