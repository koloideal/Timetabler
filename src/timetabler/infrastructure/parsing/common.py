from datetime import date, datetime, time
from typing import Iterable, Mapping

from timetabler.application.exceptions import TimetableParseError
from timetabler.domain.schemas import ParsedTimetable, TimetableEntry


def check_headers(headers: Iterable[object], required_columns: Iterable[str]) -> dict[str, str]:
    mapping = {str(h).strip().lower(): str(h) for h in headers if h is not None}
    missing = set(required_columns) - mapping.keys()
    if missing:
        raise TimetableParseError(f"Нет обязательных колонок: {', '.join(sorted(missing))}")
    return mapping


def _parse_int(raw: object, line_no: int, column: str) -> int:
    try:
        return int(float(str(raw).strip()))
    except (ValueError, TypeError):
        raise TimetableParseError(f"Строка {line_no}: {column} «{raw}» не число")


def _parse_date(raw: object, line_no: int, date_formats: tuple[str, ...]) -> date:
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    text = str(raw).strip()
    for fmt in date_formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise TimetableParseError(f"Строка {line_no}: непонятная дата «{raw}» (нужно ДД.ММ.ГГГГ)")


def _parse_time(raw: object, line_no: int, time_format: str) -> time | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.time()
    if isinstance(raw, time):
        return raw
    text = str(raw).strip()
    if text in ("", "-", "—"):
        return None
    try:
        return datetime.strptime(text, time_format).time()
    except ValueError:
        raise TimetableParseError(f"Строка {line_no}: непонятное время «{raw}» (нужно ЧЧ:ММ)")


def _parse_position(raw: object, line_no: int) -> int:
    position = _parse_int(raw, line_no, "position")
    if position <= 0:
        raise TimetableParseError(f"Строка {line_no}: position должна быть > 0")
    return position


def _opt_text(row: Mapping[str, object], header_map: dict[str, str], column: str) -> str | None:
    key = header_map.get(column)
    if key is None:
        return None
    raw = row.get(key)
    text = str(raw).strip() if raw is not None else ""
    return text if text not in ("", "-", "—") else None


def parse_rows(
    rows: Iterable[Mapping[str, object]],
    header_map: dict[str, str],
    *,
    date_formats: tuple[str, ...],
    time_format: str,
    default_date: date | None = None,
    start_line: int = 2,
) -> ParsedTimetable:
    parsed = ParsedTimetable()
    for line_no, row in enumerate(rows, start=start_line):
        raw_group = row.get(header_map["group"])
        if raw_group is None or str(raw_group).strip() == "":
            continue
        group_id = _parse_int(raw_group, line_no, "group")

        subject = str(row.get(header_map["subject"]) or "").strip()
        if not subject:
            raise TimetableParseError(f"Строка {line_no}: пустой subject")

        base_audience = _opt_text(row, header_map, "base_audience")
        if base_audience and group_id not in parsed.base_audiences:
            parsed.base_audiences[group_id] = base_audience

        raw_subgroup = _opt_text(row, header_map, "subgroup")
        raw_time = row.get(header_map["time"]) if "time" in header_map else None

        raw_date = row.get(header_map["date"]) if "date" in header_map else None
        if raw_date is not None and str(raw_date).strip():
            entry_date = _parse_date(raw_date, line_no, date_formats)
        elif default_date is not None:
            entry_date = default_date
        else:
            raise TimetableParseError(f"Строка {line_no}: пустая дата")

        parsed.entries.append(
            TimetableEntry(
                group_id=group_id,
                date=entry_date,
                position=_parse_position(row.get(header_map["position"]), line_no),
                subject=subject,
                teacher=_opt_text(row, header_map, "teacher"),
                audience=_opt_text(row, header_map, "audience"),
                starts_at=_parse_time(raw_time, line_no, time_format),
                subgroup=_parse_int(raw_subgroup, line_no, "subgroup") if raw_subgroup else None,
            )
        )
    return parsed
