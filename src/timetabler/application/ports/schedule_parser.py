from datetime import date
from typing import Protocol

from timetabler.domain.schemas import ParsedTimetable


class ScheduleParser(Protocol):
    def parse(self, values: list[list[object]], default_date: date) -> ParsedTimetable: ...
