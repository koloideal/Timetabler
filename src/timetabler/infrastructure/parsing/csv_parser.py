import csv
import io

from timetabler.application.ports import TimetableParser
from timetabler.domain.schemas import TimetableEntry
from timetabler.infrastructure.config.app import AppConfig
from timetabler.infrastructure.parsing.common import check_headers, parse_rows


class CsvTimetableParser(TimetableParser):
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def parse(self, content: bytes) -> list[TimetableEntry]:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        header_map = check_headers(reader.fieldnames or [], self.config.required_columns)
        return parse_rows(
            reader,
            header_map,
            date_formats=self.config.date_formats,
            audience_column=self.config.audience_column,
        )
