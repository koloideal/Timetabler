from datetime import date
from typing import Any

from timetabler.application.exceptions import TimetableParseError
from timetabler.domain.schemas import ParsedTimetable
from timetabler.infrastructure.config.app import AppConfig
from timetabler.infrastructure.parsing.common import check_headers, parse_rows

HEADER_SCAN_LIMIT = 10


def parse_sheet_values(values: list[list[Any]], default_date: date, config: AppConfig) -> ParsedTimetable:
    header_map: dict[str, str] | None = None
    header_row: list[Any] = []
    data_rows: list[list[Any]] = []

    for index, row in enumerate(values[:HEADER_SCAN_LIMIT]):
        try:
            header_map = check_headers(row, config.required_columns)
        except TimetableParseError:
            continue
        header_row = row
        data_rows = values[index + 1:]
        break

    if header_map is None:
        raise TimetableParseError(
            f"Не найдена строка заголовков ({', '.join(config.required_columns)})"
        )

    dict_rows = [
        {str(k): v for k, v in zip(header_row, row, strict=False) if k is not None}
        for row in data_rows
    ]
    return parse_rows(
        dict_rows,
        header_map,
        date_formats=config.date_formats,
        time_format=config.time_format,
        default_date=default_date,
        start_line=len(values) - len(data_rows) + 1,
    )
