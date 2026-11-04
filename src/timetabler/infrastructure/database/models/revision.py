from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import BigInteger, Date, ForeignKey, Index, Integer, SmallInteger, String, Time, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TimetableRevision(Base):
    __tablename__ = "timetable_revisions"
    __table_args__ = (
        Index("ix_timetable_revisions_date_status", "for_date", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    for_date: Mapped[date] = mapped_column(Date, nullable=False)
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    header: Mapped[str | None] = mapped_column(String, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    group_hashes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    base_audiences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    kind: Mapped[str] = mapped_column(String, nullable=False)
    changed_groups: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    diff: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    parent_revision_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("timetable_revisions.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    stable_polls: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    detected_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    settled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<TimetableRevision(id={self.id}, for_date={self.for_date}, kind='{self.kind}', status='{self.status}')>"


class TimetableRevisionEntry(Base):
    __tablename__ = "timetable_revision_entries"
    __table_args__ = (
        Index("ix_timetable_revision_entries_revision", "revision_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    revision_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("timetable_revisions.id", ondelete="CASCADE"), nullable=False
    )
    study_group_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("study_groups.group_id"), nullable=False
    )
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    teacher: Mapped[str | None] = mapped_column(String, nullable=True)
    audience: Mapped[str | None] = mapped_column(String, nullable=True)
    starts_at: Mapped[time | None] = mapped_column(Time, nullable=True)
    subgroup: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    def __repr__(self) -> str:
        return f"<TimetableRevisionEntry(revision={self.revision_id}, group={self.study_group_id}, pos={self.position})>"
