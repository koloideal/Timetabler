"""group chat setup fields

Revision ID: 000000000008
Revises: 000000000007
Create Date: 2026-11-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "000000000008"
down_revision: Union[str, None] = "000000000007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "group_chats",
        sa.Column("status", sa.String(), nullable=False, server_default="not_configured"),
    )
    op.add_column(
        "group_chats",
        sa.Column("study_group_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "group_chats",
        sa.Column("pin_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "group_chats",
        sa.Column("pinned_message_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "group_chats",
        sa.Column("added_by_user_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "group_chats",
        sa.Column("configured_by_user_id", sa.BigInteger(), nullable=True),
    )
    op.execute(
        "UPDATE group_chats "
        "SET study_group_id = groups[1]::bigint, status = 'active' "
        "WHERE cardinality(groups) > 0 AND groups[1] ~ '^[0-9]+$'"
    )
    op.drop_column("group_chats", "groups")


def downgrade() -> None:
    op.add_column(
        "group_chats",
        sa.Column("groups", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
    )
    op.execute(
        "UPDATE group_chats SET groups = ARRAY[study_group_id::varchar] "
        "WHERE study_group_id IS NOT NULL"
    )
    op.drop_column("group_chats", "configured_by_user_id")
    op.drop_column("group_chats", "added_by_user_id")
    op.drop_column("group_chats", "pinned_message_id")
    op.drop_column("group_chats", "pin_enabled")
    op.drop_column("group_chats", "study_group_id")
    op.drop_column("group_chats", "status")
