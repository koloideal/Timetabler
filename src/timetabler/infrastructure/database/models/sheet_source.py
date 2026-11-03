from __future__ import annotations

from sqlalchemy import SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SheetSource(Base):
    __tablename__ = "sheet_sources"

    weekday: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    spreadsheet_id: Mapped[str | None] = mapped_column(String, nullable=True)
    last_header: Mapped[str | None] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:
        return f"<SheetSource(weekday={self.weekday}, spreadsheet_id='{self.spreadsheet_id}')>"
