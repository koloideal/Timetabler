"""runtime settings table, nullable entry position

Revision ID: 000000000005
Revises: 000000000004
Create Date: 2026-11-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "000000000005"
down_revision: Union[str, None] = "000000000004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )
    op.alter_column("timetable_entries", "position", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column("timetable_entries", "position", existing_type=sa.Integer(), nullable=False)
    op.drop_table("settings")
