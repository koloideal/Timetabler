import re
from datetime import date, datetime, time

from timetabler.application.exceptions import TimetableParseError
from timetabler.domain.schemas import ParsedTimetable, TimetableEntry
from timetabler.infrastructure.config.app import AppConfig


class GridScheduleParser:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._group_re = re.compile(config.grid.group_pattern)

    def parse(self, values: list[list[object]], default_date: date) -> ParsedTimetable:
        parsed = ParsedTimetable()
        group_id: int | None = None
        grid = self.config.grid

        for row_no, raw_row in enumerate(values, start=1):
            row = list(raw_row[:grid.main_columns])
            row += [None] * (grid.main_columns - len(row))

            label = self._text(row[grid.group_col])
            if label is not None:
                match = self._group_re.match(label)
                if match:
                    group_id = int(match.group(1))
                    base_audience = self._text(match.group(2))
                    if base_audience:
                        parsed.base_audiences.setdefault(group_id, base_audience)
                else:
                    group_id = None

            subject = self._text(row[grid.subject_col])
            if group_id is None or subject is None:
                continue

            entries = self._entries(row, row_no, group_id, subject, default_date)
            parsed.entries.extend(entries)

        return parsed

    def _text(self, raw: object) -> str | None:
        if raw is None:
            return None
        if isinstance(raw, float) and raw.is_integer():
            raw = int(raw)
        text = str(raw).strip()
        return text if text not in self.config.grid.skipped_cell_values else None

    def _position(self, raw: object, row_no: int) -> int | None:
        text = self._text(raw)
        if text is None:
            return None
        try:
            return int(float(text))
        except ValueError:
            raise TimetableParseError(f"Строка {row_no}: номер пары «{text}» не число")

    def _starts_at(self, raw: object, row_no: int) -> time | None:
        if isinstance(raw, datetime):
            return raw.time()
        if isinstance(raw, time):
            return raw
        text = self._text(raw)
        if text is None:
            return None
        moved = re.search(r"[сc]\s*(\d{1,2}:\d{2})", text)
        candidates = re.findall(r"\d{1,2}:\d{2}", text)
        for candidate in ([moved.group(1)] if moved else []) + candidates:
            try:
                return datetime.strptime(candidate, self.config.time_format).time()
            except ValueError:
                continue
        raise TimetableParseError(f"Строка {row_no}: непонятное время «{text}»")

    def _entries(
        self,
        row: list[object],
        row_no: int,
        group_id: int,
        subject: str,
        default_date: date,
    ) -> list[TimetableEntry]:
        grid = self.config.grid
        position = self._position(row[grid.position_col], row_no)
        sets: list[tuple[int | None, time | None, str | None, str | None]] = [
            (
                subgroup,
                self._starts_at(row[time_col], row_no),
                self._text(row[teacher_col]),
                self._text(row[audience_col]),
            )
            for subgroup, time_col, teacher_col, audience_col in grid.subgroup_sets
        ]

        if not any(sets[1][1:]):
            sets = [(None, *sets[0][1:])]
        elif not any(sets[0][1:]):
            sets = [sets[1]]

        return [
            TimetableEntry(
                group_id=group_id,
                date=default_date,
                position=position,
                subject=subject,
                teacher=teacher,
                audience=audience,
                starts_at=starts_at,
                subgroup=subgroup,
            )
            for subgroup, starts_at, teacher, audience in sets
        ]
