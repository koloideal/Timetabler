from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import BigInteger, Date, ForeignKey, Integer, SmallInteger, String, Time, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Timetable(Base):
    __tablename__ = "timetables"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    for_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    filename: Mapped[str | None] = mapped_column(String, nullable=True)
    uploaded_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<Timetable(id={self.id}, for_date={self.for_date}, uploaded_by={self.uploaded_by})>"


class TimetableGroup(Base):
    __tablename__ = "timetable_groups"

    timetable_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("timetables.id", ondelete="CASCADE"), primary_key=True
    )
    study_group_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("study_groups.group_id"), primary_key=True
    )
    base_audience: Mapped[str | None] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:
        return f"<TimetableGroup(timetable_id={self.timetable_id}, group={self.study_group_id})>"


class TimetableEntry(Base):
    __tablename__ = "timetable_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timetable_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("timetables.id", ondelete="CASCADE"), nullable=False, index=True
    )
    study_group_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("study_groups.group_id"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    teacher: Mapped[str | None] = mapped_column(String, nullable=True)
    audience: Mapped[str | None] = mapped_column(String, nullable=True)
    starts_at: Mapped[time | None] = mapped_column(Time, nullable=True)
    subgroup: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    def __repr__(self) -> str:
        return f"<TimetableEntry(timetable={self.timetable_id}, group={self.study_group_id}, pos={self.position})>"
