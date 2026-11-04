"""timetable revisions, sent messages registry, deliveries

Revision ID: 000000000009
Revises: 000000000008
Create Date: 2026-11-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "000000000009"
down_revision: Union[str, None] = "000000000008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "timetable_revisions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("for_date", sa.Date(), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("header", sa.String(), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=True),
        sa.Column("group_hashes", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("base_audiences", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("changed_groups", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("diff", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("parent_revision_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("stable_polls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("detected_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("settled_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("published_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["parent_revision_id"], ["timetable_revisions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_timetable_revisions_date_status",
        "timetable_revisions",
        ["for_date", "status"],
    )
    op.create_table(
        "timetable_revision_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("revision_id", sa.BigInteger(), nullable=False),
        sa.Column("study_group_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("teacher", sa.String(), nullable=True),
        sa.Column("audience", sa.String(), nullable=True),
        sa.Column("starts_at", sa.Time(), nullable=True),
        sa.Column("subgroup", sa.SmallInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["timetable_revisions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["study_group_id"], ["study_groups.group_id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_timetable_revision_entries_revision",
        "timetable_revision_entries",
        ["revision_id"],
    )
    op.create_table(
        "sent_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("revision_id", sa.BigInteger(), nullable=True),
        sa.Column("for_date", sa.Date(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("groups", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
        sa.Column("sent_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["timetable_revisions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sent_messages_date_chat",
        "sent_messages",
        ["for_date", "chat_id"],
    )
    op.create_table(
        "deliveries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("revision_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("sent_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["timetable_revisions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("revision_id", "kind", "chat_id"),
    )
    op.add_column(
        "sheet_sources",
        sa.Column("last_hash", sa.String(), nullable=True),
    )

    op.execute(
        "INSERT INTO timetable_revisions "
        "(for_date, weekday, header, kind, status, detected_at, published_at) "
        "SELECT for_date, EXTRACT(isodow FROM for_date)::int - 1, filename, "
        "'new', 'published', created_at, created_at FROM timetables"
    )
    op.execute(
        "INSERT INTO timetable_revision_entries "
        "(revision_id, study_group_id, position, subject, teacher, audience, starts_at, subgroup) "
        "SELECT r.id, e.study_group_id, e.position, e.subject, e.teacher, "
        "e.audience, e.starts_at, e.subgroup "
        "FROM timetable_entries e "
        "JOIN timetables t ON t.id = e.timetable_id "
        "JOIN timetable_revisions r ON r.for_date = t.for_date"
    )
    op.execute(
        "UPDATE timetable_revisions r SET base_audiences = ("
        "SELECT COALESCE(jsonb_object_agg(g.study_group_id::text, g.base_audience), '{}'::jsonb) "
        "FROM timetable_groups g JOIN timetables t ON t.id = g.timetable_id "
        "WHERE t.for_date = r.for_date)"
    )
    op.execute(
        "UPDATE timetable_revisions r SET changed_groups = ("
        "SELECT COALESCE(jsonb_agg(DISTINCT e.study_group_id), '[]'::jsonb) "
        "FROM timetable_revision_entries e WHERE e.revision_id = r.id)"
    )

    op.drop_table("timetable_entries")
    op.drop_table("timetable_groups")
    op.drop_table("timetables")


def downgrade() -> None:
    op.create_table(
        "timetables",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("for_date", sa.Date(), nullable=False),
        sa.Column("filename", sa.String(), nullable=True),
        sa.Column("uploaded_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("for_date"),
    )
    op.create_table(
        "timetable_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("timetable_id", sa.BigInteger(), nullable=False),
        sa.Column("study_group_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("teacher", sa.String(), nullable=True),
        sa.Column("audience", sa.String(), nullable=True),
        sa.Column("starts_at", sa.Time(), nullable=True),
        sa.Column("subgroup", sa.SmallInteger(), nullable=True),
        sa.ForeignKeyConstraint(["timetable_id"], ["timetables.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "timetable_groups",
        sa.Column("timetable_id", sa.BigInteger(), nullable=False),
        sa.Column("study_group_id", sa.BigInteger(), nullable=False),
        sa.Column("base_audience", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["timetable_id"], ["timetables.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["study_group_id"], ["study_groups.group_id"]),
        sa.PrimaryKeyConstraint("timetable_id", "study_group_id"),
    )
    op.execute(
        "INSERT INTO timetables (for_date, filename, uploaded_by, created_at) "
        "SELECT DISTINCT ON (for_date) for_date, header, "
        "COALESCE((SELECT min(user_id) FROM users), 0), detected_at "
        "FROM timetable_revisions WHERE status = 'published' "
        "ORDER BY for_date, id DESC"
    )
    op.execute(
        "INSERT INTO timetable_entries "
        "(timetable_id, study_group_id, position, subject, teacher, audience, starts_at, subgroup) "
        "SELECT t.id, e.study_group_id, e.position, e.subject, e.teacher, "
        "e.audience, e.starts_at, e.subgroup "
        "FROM timetable_revision_entries e "
        "JOIN timetable_revisions r ON r.id = e.revision_id "
        "JOIN timetables t ON t.for_date = r.for_date "
        "WHERE r.status = 'published'"
    )

    op.drop_column("sheet_sources", "last_hash")
    op.drop_table("deliveries")
    op.drop_table("sent_messages")
    op.drop_table("timetable_revision_entries")
    op.drop_table("timetable_revisions")
