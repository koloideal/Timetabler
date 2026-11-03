from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, String, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class StudyGroup(Base):
    __tablename__ = "study_groups"

    group_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    alias: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<StudyGroup(group_id={self.group_id}, alias='{self.alias}')>"
