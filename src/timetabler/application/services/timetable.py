from dataclasses import dataclass
from datetime import date
from pathlib import Path

from timetabler.application.exceptions import TimetableParseError
from timetabler.application.ports import TimetableParser
from timetabler.application.services.study_group import StudyGroupService
from timetabler.infrastructure.database.dao import TimetableEntriesDAO


@dataclass
class ImportResult:
    dates: list[date]
    lessons: int
    groups: int


class TimetableService:
    def __init__(
        self,
        timetable_entries_dao: TimetableEntriesDAO,
        study_group_service: StudyGroupService,
        parsers: dict[str, TimetableParser],
    ) -> None:
        self.timetable_entries_dao = timetable_entries_dao
        self.study_group_service = study_group_service
        self.parsers = parsers

    async def import_document(self, filename: str, content: bytes) -> ImportResult:
        extension = Path(filename).suffix.lower()
        parser = self.parsers.get(extension)
        if parser is None:
            raise TimetableParseError(f"Неподдерживаемый формат «{extension}»")

        entries = parser.parse(content)
        if not entries:
            raise TimetableParseError("Файл пустой — не найдено ни одной пары")

        known_groups = {g.group_id for g in await self.study_group_service.list_groups()}
        unknown = sorted(
            {entry.group for entry in entries if int(entry.group) not in known_groups}
        )
        if unknown:
            raise TimetableParseError(
                f"Неизвестные группы: {', '.join(unknown)}.\nСначала добавьте их через /admin → 📚 Группы"
            )

        dates = {entry.date for entry in entries}
        await self.timetable_entries_dao.replace_for_dates(dates, entries)

        return ImportResult(
            dates=sorted(dates),
            lessons=len(entries),
            groups=len({entry.group for entry in entries}),
        )
