"""user subgroup mode preference

Revision ID: 000000000011
Revises: 000000000010
Create Date: 2026-11-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "000000000011"
down_revision: Union[str, None] = "000000000010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("subgroup_mode", sa.String(), nullable=False, server_default="a"),
    )


def downgrade() -> None:
    op.drop_column("users", "subgroup_mode")
