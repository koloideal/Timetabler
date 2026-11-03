from dataclasses import dataclass
from datetime import date

from timetabler.application.exceptions import TimetableParseError
from timetabler.application.services.study_group import StudyGroupService
from timetabler.domain.schemas import ParsedTimetable
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
    ) -> None:
        self.timetables_dao = timetables_dao
        self.study_group_service = study_group_service

    async def import_parsed(
        self, parsed: ParsedTimetable, source: str, uploaded_by: int
    ) -> ImportResult:
        if not parsed.entries:
            raise TimetableParseError("Нет ни одной пары")

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
                source,
                uploaded_by,
                ParsedTimetable(entries=day_entries, base_audiences=parsed.base_audiences),
            )

        return ImportResult(
            dates=sorted(dates),
            lessons=len(parsed.entries),
            groups=len({entry.group_id for entry in parsed.entries}),
        )
