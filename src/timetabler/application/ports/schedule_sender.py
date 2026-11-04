from datetime import date
from typing import Protocol

from timetabler.domain.schemas import DaySchedule


class ScheduleSender(Protocol):
    async def send_group_schedule(
        self, chat_id: int, for_date: date, day: DaySchedule, group_id: int
    ) -> bool: ...

    async def send_channel_schedule(
        self, chat_id: int, for_date: date, day: DaySchedule
    ) -> bool: ...
