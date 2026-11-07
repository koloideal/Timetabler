"""user main group

Revision ID: 000000000014
Revises: 000000000013
Create Date: 2026-11-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "000000000014"
down_revision: Union[str, None] = "000000000013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("main_group", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_main_group",
        "users",
        "study_groups",
        ["main_group"],
        ["group_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_main_group", "users", type_="foreignkey")
    op.drop_column("users", "main_group")
