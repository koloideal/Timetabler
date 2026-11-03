from dataclasses import dataclass
from datetime import date
from pathlib import Path

from timetabler.application.exceptions import TimetableParseError
from timetabler.application.ports import TimetableParser
from timetabler.domain.schemas import ParsedTimetable
from timetabler.application.services.study_group import StudyGroupService
from timetabler.infrastructure.database.dao import TimetablesDAO


@dataclass
class ImportResult:
    dates: list[date]
    lessons: int
    groups: int


class TimetableService:
    def __init__(
        self,
        timetables_dao: TimetablesDAO,
        study_group_service: StudyGroupService,
        parsers: dict[str, TimetableParser],
    ) -> None:
        self.timetables_dao = timetables_dao
        self.study_group_service = study_group_service
        self.parsers = parsers

    async def import_document(self, filename: str, content: bytes, uploaded_by: int) -> ImportResult:
        extension = Path(filename).suffix.lower()
        parser = self.parsers.get(extension)
        if parser is None:
            raise TimetableParseError(f"Неподдерживаемый формат «{extension}»")

        parsed = parser.parse(content)
        if not parsed.entries:
            raise TimetableParseError("Файл пустой — не найдено ни одной пары")

        known_groups = {g.group_id for g in await self.study_group_service.list_groups()}
        unknown = sorted(
            {entry.group_id for entry in parsed.entries if entry.group_id not in known_groups}
        )
        if unknown:
            raise TimetableParseError(
                f"Неизвестные группы: {', '.join(str(g) for g in unknown)}.\nСначала добавьте их через /admin → 📚 Группы"
            )

        dates = {entry.date for entry in parsed.entries}
        for for_date in sorted(dates):
            day_entries = [e for e in parsed.entries if e.date == for_date]
            await self.timetables_dao.replace(
                for_date,
                filename,
                uploaded_by,
                ParsedTimetable(entries=day_entries, base_audiences=parsed.base_audiences),
            )

        return ImportResult(
            dates=sorted(dates),
            lessons=len(parsed.entries),
            groups=len({entry.group_id for entry in parsed.entries}),
        )
