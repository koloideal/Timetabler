from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from timetabler.domain.schemas import TimetableEntry
from timetabler.infrastructure.database.models import TimetableEntry as OrmTimetableEntry


class TimetableEntriesDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def replace_for_dates(self, dates: set[date], entries: list[TimetableEntry]) -> None:
        await self.session.execute(
            delete(OrmTimetableEntry).where(OrmTimetableEntry.date.in_(dates))
        )
        self.session.add_all(
            OrmTimetableEntry(
                date=entry.date,
                group=entry.group,
                position=entry.position,
                subject=entry.subject,
                audience=entry.audience,
            )
            for entry in entries
        )
        await self.session.flush()

    async def get_by_date(self, target_date: date) -> list[TimetableEntry]:
        query = (
            select(OrmTimetableEntry)
            .where(OrmTimetableEntry.date == target_date)
            .order_by(OrmTimetableEntry.group, OrmTimetableEntry.position)
        )
        result = await self.session.execute(query)
        return [self._map_to_domain(e) for e in result.scalars().all()]

    async def list_dates(self) -> list[date]:
        query = select(OrmTimetableEntry.date).distinct().order_by(OrmTimetableEntry.date)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    def _map_to_domain(orm_entry: OrmTimetableEntry) -> TimetableEntry:
        return TimetableEntry(
            date=orm_entry.date,
            group=orm_entry.group,
            position=orm_entry.position,
            subject=orm_entry.subject,
            audience=orm_entry.audience,
        )
