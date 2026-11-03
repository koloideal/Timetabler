from io import BytesIO

from openpyxl import load_workbook

from timetabler.application.ports import TimetableParser
from timetabler.domain.schemas import TimetableEntry
from timetabler.infrastructure.config.app import AppConfig
from timetabler.infrastructure.parsing.common import check_headers, parse_rows


class XlsxTimetableParser(TimetableParser):
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def parse(self, content: bytes) -> list[TimetableEntry]:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        sheet = workbook.worksheets[0]
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return []

        header_map = check_headers(rows[0], self.config.required_columns)
        dict_rows = [
            {str(k): v for k, v in zip(rows[0], row, strict=False) if k is not None}
            for row in rows[1:]
        ]
        return parse_rows(
            dict_rows,
            header_map,
            date_formats=self.config.date_formats,
            audience_column=self.config.audience_column,
        )
