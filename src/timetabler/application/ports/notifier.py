from datetime import date
from typing import Protocol

from timetabler.domain.schemas import BroadcastSummary, DaySchedule


class CreatorNotifier(Protocol):
    async def ask_broadcast_confirmation(self, for_date: date, day: DaySchedule) -> None: ...

    async def notify_schedule_updated(self, summary: BroadcastSummary) -> None: ...
