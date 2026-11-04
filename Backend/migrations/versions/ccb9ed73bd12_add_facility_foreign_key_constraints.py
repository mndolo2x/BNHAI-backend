"""add facility foreign key constraints

Revision ID: ccb9ed73bd12
Revises: d01350d65b16
Create Date: 2026-11-04 18:40:16.399738
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'ccb9ed73bd12'
down_revision: Union[str, None] = 'd01350d65b16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table_name in (
        "patients",
        "encounters",
        "user_facility_roles",
    ):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.create_foreign_key(
                f"fk_{table_name}_facility_id",
                "facilities",
                ["facility_id"],
                ["facility_id"],
                ondelete="RESTRICT",
            )


def downgrade() -> None:
    for table_name in (
        "user_facility_roles",
        "encounters",
        "patients",
    ):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(
                f"fk_{table_name}_facility_id",
                type_="foreignkey",
            )
