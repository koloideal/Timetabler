"""resolved lesson timing columns

Revision ID: 000000000012
Revises: 000000000011
Create Date: 2026-11-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "000000000012"
down_revision: Union[str, None] = "000000000011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "timetable_revision_entries",
        sa.Column("ordinal", sa.Integer(), nullable=True),
    )
    op.add_column(
        "timetable_revision_entries",
        sa.Column("slot", sa.SmallInteger(), nullable=True),
    )
    op.add_column(
        "timetable_revision_entries",
        sa.Column("half", sa.String(), nullable=True),
    )
    op.add_column(
        "timetable_revision_entries",
        sa.Column("start_sec", sa.Integer(), nullable=True),
    )
    op.add_column(
        "timetable_revision_entries",
        sa.Column("end_sec", sa.Integer(), nullable=True),
    )
    op.add_column(
        "timetable_revision_entries",
        sa.Column("kind", sa.String(), nullable=True),
    )
    op.add_column(
        "timetable_revision_entries",
        sa.Column("flags", JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("timetable_revision_entries", "flags")
    op.drop_column("timetable_revision_entries", "kind")
    op.drop_column("timetable_revision_entries", "end_sec")
    op.drop_column("timetable_revision_entries", "start_sec")
    op.drop_column("timetable_revision_entries", "half")
    op.drop_column("timetable_revision_entries", "slot")
    op.drop_column("timetable_revision_entries", "ordinal")
