from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from timetabler.domain.schemas import ParsedTimetable, Timetable
from timetabler.infrastructure.database.models import (
    Timetable as OrmTimetable,
)
from timetabler.infrastructure.database.models import (
    TimetableEntry as OrmTimetableEntry,
)
from timetabler.infrastructure.database.models import (
    TimetableGroup as OrmTimetableGroup,
)


class TimetablesDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def replace(
        self,
        for_date: date,
        filename: str,
        uploaded_by: int,
        parsed: ParsedTimetable,
    ) -> None:
        await self.session.execute(
            delete(OrmTimetable).where(OrmTimetable.for_date == for_date)
        )

        orm_timetable = OrmTimetable(
            for_date=for_date,
            filename=filename,
            uploaded_by=uploaded_by,
        )
        self.session.add(orm_timetable)
        await self.session.flush()

        for group_id, base_audience in parsed.base_audiences.items():
            self.session.add(
                OrmTimetableGroup(
                    timetable_id=orm_timetable.id,
                    study_group_id=group_id,
                    base_audience=base_audience,
                )
            )

        for entry in parsed.entries:
            self.session.add(
                OrmTimetableEntry(
                    timetable_id=orm_timetable.id,
                    study_group_id=entry.group_id,
                    position=entry.position,
                    subject=entry.subject,
                    teacher=entry.teacher,
                    audience=entry.audience,
                    starts_at=entry.starts_at,
                    subgroup=entry.subgroup,
                )
            )
        await self.session.flush()

    async def get_by_date(self, for_date: date) -> Timetable | None:
        query = select(OrmTimetable).where(OrmTimetable.for_date == for_date)
        result = await self.session.execute(query)
        orm_timetable = result.scalar_one_or_none()

        if orm_timetable:
            return self._map_to_domain(orm_timetable)

        return None

    async def list_dates(self) -> list[date]:
        query = select(OrmTimetable.for_date).order_by(OrmTimetable.for_date)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    def _map_to_domain(orm_timetable: OrmTimetable) -> Timetable:
        return Timetable(
            id=orm_timetable.id,
            for_date=orm_timetable.for_date,
            filename=orm_timetable.filename,
            uploaded_by=orm_timetable.uploaded_by,
            created_at=orm_timetable.created_at,
        )
