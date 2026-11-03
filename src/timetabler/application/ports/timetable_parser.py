from typing import Protocol

from timetabler.domain.schemas import ParsedTimetable


class TimetableParser(Protocol):
    def parse(self, content: bytes) -> ParsedTimetable: ...
