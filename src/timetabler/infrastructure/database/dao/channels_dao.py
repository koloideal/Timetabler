from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from timetabler.domain.schemas import Channel
from timetabler.infrastructure.database.models import Channel as OrmChannel


class ChannelsDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, chat_id: int) -> Channel | None:
        query = select(OrmChannel).where(OrmChannel.chat_id == chat_id)
        result = await self.session.execute(query)
        orm_channel = result.scalar_one_or_none()

        if orm_channel:
            return self._map_to_domain(orm_channel)

        return None

    async def get_all(self) -> list[Channel]:
        query = select(OrmChannel).order_by(OrmChannel.created_at)
        result = await self.session.execute(query)
        return [self._map_to_domain(c) for c in result.scalars().all()]

    async def get_enabled(self) -> list[Channel]:
        query = select(OrmChannel).where(OrmChannel.status == "approved")
        result = await self.session.execute(query)
        return [self._map_to_domain(c) for c in result.scalars().all()]

    async def upsert_pending(self, chat_id: int, title: str | None) -> Channel | None:
        stmt = (
            insert(OrmChannel)
            .values(chat_id=chat_id, title=title, status="pending")
            .on_conflict_do_update(
                index_elements=["chat_id"],
                set_={"title": title, "status": "pending"},
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()

        return await self.get_by_id(chat_id)

    async def set_status(self, chat_id: int, status: str) -> Channel | None:
        stmt = (
            update(OrmChannel)
            .where(OrmChannel.chat_id == chat_id)
            .values(status=status)
            .returning(OrmChannel)
        )
        result = await self.session.execute(stmt)
        orm_channel = result.scalar_one_or_none()

        if not orm_channel:
            return None

        return self._map_to_domain(orm_channel)

    async def remove(self, chat_id: int) -> bool:
        stmt = delete(OrmChannel).where(OrmChannel.chat_id == chat_id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    @staticmethod
    def _map_to_domain(orm_channel: OrmChannel) -> Channel:
        return Channel(
            chat_id=orm_channel.chat_id,
            title=orm_channel.title,
            status=orm_channel.status,
            created_at=orm_channel.created_at,
        )
