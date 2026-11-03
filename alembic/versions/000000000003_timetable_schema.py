"""timetable schema rework

Revision ID: 000000000003
Revises: 000000000002
Create Date: 2026-11-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "000000000003"
down_revision: Union[str, None] = "000000000002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_timetable_entries_group", table_name="timetable_entries")
    op.drop_table("timetable_entries")

    op.create_table(
        "timetables",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("for_date", sa.Date(), nullable=False),
        sa.Column("filename", sa.String(), nullable=True),
        sa.Column("uploaded_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("for_date"),
    )
    op.create_table(
        "timetable_groups",
        sa.Column("timetable_id", sa.BigInteger(), nullable=False),
        sa.Column("study_group_id", sa.BigInteger(), nullable=False),
        sa.Column("base_audience", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["study_group_id"], ["study_groups.group_id"]),
        sa.ForeignKeyConstraint(["timetable_id"], ["timetables.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("timetable_id", "study_group_id"),
    )
    op.create_table(
        "timetable_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("timetable_id", sa.BigInteger(), nullable=False),
        sa.Column("study_group_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("teacher", sa.String(), nullable=True),
        sa.Column("audience", sa.String(), nullable=True),
        sa.Column("starts_at", sa.Time(), nullable=True),
        sa.Column("subgroup", sa.SmallInteger(), nullable=True),
        sa.ForeignKeyConstraint(["study_group_id"], ["study_groups.group_id"]),
        sa.ForeignKeyConstraint(["timetable_id"], ["timetables.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_timetable_entries_timetable_id", "timetable_entries", ["timetable_id"])
    op.create_index("ix_timetable_entries_study_group_id", "timetable_entries", ["study_group_id"])


def downgrade() -> None:
    op.drop_table("timetable_entries")
    op.drop_table("timetable_groups")
    op.drop_table("timetables")

    op.create_table(
        "timetable_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("group", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("audience", sa.String(), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_timetable_entries_group", "timetable_entries", ["group"])
