from datetime import date, datetime
from typing import Iterable, Mapping

from timetabler.application.exceptions import TimetableParseError
from timetabler.domain.schemas import TimetableEntry


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


def _parse_position(raw: object, line_no: int) -> int:
    position = _parse_int(raw, line_no, "position")
    if position <= 0:
        raise TimetableParseError(f"Строка {line_no}: position должна быть > 0")
    return position


def parse_rows(
    rows: Iterable[Mapping[str, object]],
    header_map: dict[str, str],
    *,
    date_formats: tuple[str, ...],
    audience_column: str,
) -> list[TimetableEntry]:
    entries: list[TimetableEntry] = []
    for line_no, row in enumerate(rows, start=2):
        raw_group = row.get(header_map["group"])
        if raw_group is None or str(raw_group).strip() == "":
            continue
        group_id = _parse_int(raw_group, line_no, "group")

        subject = str(row.get(header_map["subject"]) or "").strip()
        if not subject:
            raise TimetableParseError(f"Строка {line_no}: пустой subject")

        raw_audience = row.get(header_map.get(audience_column, ""))
        audience_text = str(raw_audience).strip() if raw_audience is not None else ""
        audience = audience_text if audience_text not in ("", "-", "—") else None

        entries.append(
            TimetableEntry(
                date=_parse_date(row.get(header_map["date"]), line_no, date_formats),
                group=str(group_id),
                position=_parse_position(row.get(header_map["position"]), line_no),
                subject=subject,
                audience=audience,
            )
        )
    return entries
