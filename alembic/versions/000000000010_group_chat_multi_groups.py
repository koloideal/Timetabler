"""group chats: multiple study groups, pinned message ids

Revision ID: 000000000010
Revises: 000000000009
Create Date: 2026-11-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "000000000010"
down_revision: Union[str, None] = "000000000009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "group_chats",
        sa.Column(
            "study_groups",
            postgresql.ARRAY(sa.BigInteger()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE group_chats SET study_groups = ARRAY[study_group_id] "
        "WHERE study_group_id IS NOT NULL"
    )
    op.drop_column("group_chats", "study_group_id")
    op.add_column(
        "group_chats",
        sa.Column(
            "pinned_message_ids",
            postgresql.ARRAY(sa.BigInteger()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE group_chats SET pinned_message_ids = ARRAY[pinned_message_id] "
        "WHERE pinned_message_id IS NOT NULL"
    )
    op.drop_column("group_chats", "pinned_message_id")


def downgrade() -> None:
    op.add_column("group_chats", sa.Column("pinned_message_id", sa.BigInteger(), nullable=True))
    op.execute(
        "UPDATE group_chats SET pinned_message_id = pinned_message_ids[1] "
        "WHERE cardinality(pinned_message_ids) > 0"
    )
    op.drop_column("group_chats", "pinned_message_ids")
    op.add_column("group_chats", sa.Column("study_group_id", sa.BigInteger(), nullable=True))
    op.execute(
        "UPDATE group_chats SET study_group_id = study_groups[1] "
        "WHERE cardinality(study_groups) > 0"
    )
    op.drop_column("group_chats", "study_groups")
