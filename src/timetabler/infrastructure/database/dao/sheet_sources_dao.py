from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from timetabler.domain.schemas import SheetSource
from timetabler.infrastructure.database.models import SheetSource as OrmSheetSource


class SheetSourcesDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_weekday(self, weekday: int) -> SheetSource | None:
        query = select(OrmSheetSource).where(OrmSheetSource.weekday == weekday)
        result = await self.session.execute(query)
        orm_source = result.scalar_one_or_none()

        if orm_source:
            return self._map_to_domain(orm_source)

        return None

    async def get_all(self) -> list[SheetSource]:
        query = select(OrmSheetSource).order_by(OrmSheetSource.weekday)
        result = await self.session.execute(query)
        return [self._map_to_domain(s) for s in result.scalars().all()]

    async def set_spreadsheet(self, weekday: int, spreadsheet_id: str | None) -> None:
        stmt = (
            insert(OrmSheetSource)
            .values(weekday=weekday, spreadsheet_id=spreadsheet_id, last_header=None, last_hash=None)
            .on_conflict_do_update(
                index_elements=["weekday"],
                set_={"spreadsheet_id": spreadsheet_id, "last_header": None, "last_hash": None},
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def set_last_header(self, weekday: int, last_header: str) -> None:
        stmt = (
            update(OrmSheetSource)
            .where(OrmSheetSource.weekday == weekday)
            .values(last_header=last_header)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def set_last_hash(self, weekday: int, last_hash: str) -> None:
        stmt = (
            update(OrmSheetSource)
            .where(OrmSheetSource.weekday == weekday)
            .values(last_hash=last_hash)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    @staticmethod
    def _map_to_domain(orm_source: OrmSheetSource) -> SheetSource:
        return SheetSource(
            weekday=orm_source.weekday,
            spreadsheet_id=orm_source.spreadsheet_id,
            last_header=orm_source.last_header,
            last_hash=orm_source.last_hash,
        )
