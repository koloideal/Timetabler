"""channels table

Revision ID: 000000000007
Revises: 000000000006
Create Date: 2026-11-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "000000000007"
down_revision: Union[str, None] = "000000000006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("chat_id"),
    )


def downgrade() -> None:
    op.drop_table("channels")
