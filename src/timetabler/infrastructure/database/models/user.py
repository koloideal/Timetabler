from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import ARRAY, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    main_group: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("study_groups.group_id", ondelete="SET NULL"), nullable=True
    )
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    groups: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list, server_default="{}")
    subgroup_mode: Mapped[str] = mapped_column(String, nullable=False, default="a", server_default="a")
    pin_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    pinned_message_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), nullable=False, default=list, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<User(user_id={self.user_id}, username='{self.username}', groups={self.groups})>"
