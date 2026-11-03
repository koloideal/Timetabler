from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, String, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Channel(Base):
    __tablename__ = "channels"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<Channel(chat_id={self.chat_id}, title='{self.title}', status='{self.status}')>"
