"""convert claim amounts to numeric

Revision ID: d01350d65b16
Revises: 0007_claims_capture
Create Date: 2026-11-04 00:08:17.411553
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd01350d65b16'
down_revision: Union[str, None] = '0007_claims_capture'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("claim_batches") as batch_op:
        batch_op.alter_column(
            "total_amount",
            existing_type=sa.Float(),
            type_=sa.Numeric(precision=12, scale=2),
            existing_nullable=False,
        )

    with op.batch_alter_table("claim_documents") as batch_op:
        batch_op.alter_column(
            "amount",
            existing_type=sa.Float(),
            type_=sa.Numeric(precision=12, scale=2),
            existing_nullable=True,
        )

def downgrade() -> None:
    with op.batch_alter_table("claim_documents") as batch_op:
        batch_op.alter_column(
            "amount",
            existing_type=sa.Numeric(precision=12, scale=2),
            type_=sa.Float(),
            existing_nullable=True,
        )

    with op.batch_alter_table("claim_batches") as batch_op:
        batch_op.alter_column(
            "total_amount",
            existing_type=sa.Numeric(precision=12, scale=2),
            type_=sa.Float(),
            existing_nullable=False,
        )
