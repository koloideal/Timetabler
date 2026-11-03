from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from timetabler.domain.schemas import StudyGroup
from timetabler.infrastructure.database.models import StudyGroup as OrmStudyGroup


class StudyGroupsDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, group_id: int) -> StudyGroup | None:
        query = select(OrmStudyGroup).where(OrmStudyGroup.group_id == group_id)
        result = await self.session.execute(query)
        orm_group = result.scalar_one_or_none()

        if orm_group:
            return self._map_to_domain(orm_group)

        return None

    async def get_all(self) -> list[StudyGroup]:
        query = select(OrmStudyGroup).order_by(OrmStudyGroup.group_id)
        result = await self.session.execute(query)
        return [self._map_to_domain(g) for g in result.scalars().all()]

    async def create(self, group_id: int, alias: str | None) -> StudyGroup | None:
        stmt = (
            insert(OrmStudyGroup)
            .values(group_id=group_id, alias=alias)
            .on_conflict_do_nothing(index_elements=["group_id"])
        )
        await self.session.execute(stmt)
        await self.session.flush()

        return await self.get_by_id(group_id)

    async def set_alias(self, group_id: int, alias: str | None) -> StudyGroup | None:
        stmt = (
            update(OrmStudyGroup)
            .where(OrmStudyGroup.group_id == group_id)
            .values(alias=alias)
        )
        await self.session.execute(stmt)
        await self.session.flush()

        return await self.get_by_id(group_id)

    async def remove(self, group_id: int) -> bool:
        stmt = delete(OrmStudyGroup).where(OrmStudyGroup.group_id == group_id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    @staticmethod
    def _map_to_domain(orm_group: OrmStudyGroup) -> StudyGroup:
        return StudyGroup(
            group_id=orm_group.group_id,
            alias=orm_group.alias,
            created_at=orm_group.created_at,
        )
