"""sheets sources, drop admin role

Revision ID: 000000000004
Revises: 000000000003
Create Date: 2026-11-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "000000000004"
down_revision: Union[str, None] = "000000000003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sheet_sources",
        sa.Column("weekday", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("spreadsheet_id", sa.String(), nullable=True),
        sa.Column("last_header", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("weekday"),
    )
    op.drop_column("users", "is_admin")


def downgrade() -> None:
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), server_default="false", nullable=False))
    op.drop_table("sheet_sources")
