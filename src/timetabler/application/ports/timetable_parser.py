from typing import Protocol

from timetabler.domain.schemas import TimetableEntry


class TimetableParser(Protocol):
    def parse(self, content: bytes) -> list[TimetableEntry]: ...
