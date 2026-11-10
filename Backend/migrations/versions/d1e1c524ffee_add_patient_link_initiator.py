"""add patient link initiator

Revision ID: d1e1c524ffee
Revises: 8cfe36edd109
Create Date: 2026-11-09 15:31:02.641623
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd1e1c524ffee'
down_revision: Union[str, None] = '8cfe36edd109'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE patient_account_links "
            "ADD COLUMN created_by VARCHAR(36) "
            "REFERENCES users(user_id) ON DELETE RESTRICT"
        )
    else:
        op.add_column(
            "patient_account_links",
            sa.Column(
                "created_by",
                sa.String(36),
                nullable=True,
            ),
        )

        op.create_foreign_key(
            "fk_patient_account_links_created_by_users",
            "patient_account_links",
            "users",
            ["created_by"],
            ["user_id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint(
            "fk_patient_account_links_created_by_users",
            "patient_account_links",
            type_="foreignkey",
        )

    op.drop_column(
        "patient_account_links",
        "created_by",
    )
