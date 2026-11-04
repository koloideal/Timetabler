from dataclasses import dataclass
from datetime import date
from typing import Protocol

from timetabler.domain.schemas import DaySchedule


@dataclass
class ChatDelivery:
    message_id: int | None = None
    migrate_to: int | None = None
    failed: bool = False


class ScheduleSender(Protocol):
    async def send_group_schedule(
        self, chat_id: int, for_date: date, day: DaySchedule, group_id: int,
        note: str | None = None, mode: str = "a",
    ) -> int | None: ...

    async def send_channel_schedule(
        self, chat_id: int, for_date: date, day: DaySchedule, note: str | None = None
    ) -> int | None: ...

    async def edit_channel_schedule(
        self, chat_id: int, message_id: int, for_date: date, day: DaySchedule,
        note: str | None = None,
    ) -> bool: ...

    async def send_chat_schedule(
        self, chat_id: int, for_date: date, day: DaySchedule, group_id: int,
        note: str | None = None,
    ) -> ChatDelivery: ...

    async def delete_message(self, chat_id: int, message_id: int) -> None: ...

    async def pin_chat_message(self, chat_id: int, message_id: int) -> bool: ...

    async def unpin_chat_message(self, chat_id: int, message_id: int) -> None: ...

    async def send_text(self, chat_id: int, text: str) -> bool: ...
