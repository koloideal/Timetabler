from sqlalchemy import delete, literal, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from timetabler.domain.schemas import GroupChat
from timetabler.infrastructure.database.models import GroupChat as OrmGroupChat


class GroupChatsDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, chat_id: int) -> GroupChat | None:
        query = select(OrmGroupChat).where(OrmGroupChat.chat_id == chat_id)
        result = await self.session.execute(query)
        orm_chat = result.scalar_one_or_none()

        if orm_chat:
            return self._map_to_domain(orm_chat)

        return None

    async def upsert(self, chat_id: int, title: str | None) -> GroupChat | None:
        stmt = (
            insert(OrmGroupChat)
            .values(chat_id=chat_id, title=title)
            .on_conflict_do_update(index_elements=["chat_id"], set_=dict(title=title))
        )
        await self.session.execute(stmt)
        await self.session.flush()

        return await self.get_by_id(chat_id)

    async def get_all(self) -> list[GroupChat]:
        query = select(OrmGroupChat)
        result = await self.session.execute(query)
        return [self._map_to_domain(c) for c in result.scalars().all()]

    async def get_subscribed_to_group(self, group: str) -> list[GroupChat]:
        query = select(OrmGroupChat).where(OrmGroupChat.groups.any(literal(group)))
        result = await self.session.execute(query)
        return [self._map_to_domain(c) for c in result.scalars().all()]

    async def update_groups(self, chat_id: int, groups: list[str]) -> GroupChat | None:
        stmt = (
            update(OrmGroupChat)
            .where(OrmGroupChat.chat_id == chat_id)
            .values(groups=groups)
            .returning(OrmGroupChat)
        )
        result = await self.session.execute(stmt)
        orm_chat = result.scalar_one_or_none()

        if not orm_chat:
            return None

        return self._map_to_domain(orm_chat)

    async def remove(self, chat_id: int) -> bool:
        stmt = delete(OrmGroupChat).where(OrmGroupChat.chat_id == chat_id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    @staticmethod
    def _map_to_domain(orm_chat: OrmGroupChat) -> GroupChat:
        return GroupChat(
            chat_id=orm_chat.chat_id,
            title=orm_chat.title,
            groups=list(orm_chat.groups),
            created_at=orm_chat.created_at,
        )
