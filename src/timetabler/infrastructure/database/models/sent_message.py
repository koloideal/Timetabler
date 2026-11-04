from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SentMessage(Base):
    __tablename__ = "sent_messages"
    __table_args__ = (
        Index("ix_sent_messages_date_chat", "for_date", "chat_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    revision_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("timetable_revisions.id", ondelete="SET NULL"), nullable=True
    )
    for_date: Mapped[date] = mapped_column(Date, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    groups: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list, server_default="{}")
    sent_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<SentMessage(chat_id={self.chat_id}, for_date={self.for_date}, kind='{self.kind}')>"
