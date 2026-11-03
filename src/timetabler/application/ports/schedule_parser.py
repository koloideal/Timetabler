from datetime import date
from typing import Any, Protocol

from timetabler.domain.schemas import ParsedTimetable


class ScheduleParser(Protocol):
    def parse(self, values: list[list[Any]], default_date: date) -> ParsedTimetable: ...
