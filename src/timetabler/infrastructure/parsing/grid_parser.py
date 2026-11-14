import logging
import re
from datetime import date, datetime, time

from timetabler.application.exceptions import TimetableParseError
from timetabler.domain.schemas import ParsedTimetable, TimetableEntry
from timetabler.infrastructure.config.app import AppConfig


class GridScheduleParser:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._group_re = re.compile(config.grid.group_pattern)
        self._boundary_re = re.compile(config.grid.boundary_pattern, re.IGNORECASE)
        self._logger = logging.getLogger(__name__)

    def parse(self, values: list[list[object]], default_date: date) -> ParsedTimetable:
        parsed = ParsedTimetable()
        group_id: int | None = None
        seen_group = False
        grid = self.config.grid

        for row_no, raw_row in enumerate(values, start=1):
            row = list(raw_row[:grid.main_columns])
            row += [None] * (grid.main_columns - len(row))

            label = self._text(row[grid.group_col])
            if label is not None:
                if self._boundary_re.match(label):
                    if seen_group:
                        self._logger.info(
                            "Grid truncated at row %s: repeated document header %r",
                            row_no, label,
                        )
                        break
                    group_id = None
                    continue
                match = self._group_re.match(label)
                if match:
                    group_id = int(re.sub(r"\s+", "", match.group(1)))
                    seen_group = True
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
        moved = re.search(r"[сc]\s*(\d{1,2}\s*:\s*\d{2})", text)
        candidates = re.findall(r"\d{1,2}\s*:\s*\d{2}", text)
        for candidate in ([moved.group(1)] if moved else []) + candidates:
            candidate = re.sub(r"\s+", "", candidate)
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

        s1, s2 = sets
        s1_lesson = s1[1] is not None or s1[2] is not None
        s2_lesson = s2[1] is not None or s2[2] is not None
        if s1_lesson and s2_lesson:
            pass
        elif s2_lesson:
            sets = [(s2[0], s2[1], s2[2], s2[3] or s1[3])]
        else:
            sets = [(None, s1[1], s1[2], s1[3] or s2[3])]

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
