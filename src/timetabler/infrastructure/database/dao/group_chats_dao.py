from sqlalchemy import case, delete, select, update
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

    async def upsert(self, chat_id: int, title: str | None, added_by_user_id: int | None) -> GroupChat | None:
        stmt = (
            insert(OrmGroupChat)
            .values(chat_id=chat_id, title=title, added_by_user_id=added_by_user_id)
            .on_conflict_do_update(
                index_elements=["chat_id"],
                set_={
                    "title": title,
                    "added_by_user_id": added_by_user_id,
                    "status": case(
                        (OrmGroupChat.status == "disabled", "not_configured"),
                        else_=OrmGroupChat.status,
                    ),
                },
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()

        return await self.get_by_id(chat_id)

    async def get_all(self) -> list[GroupChat]:
        query = select(OrmGroupChat).order_by(OrmGroupChat.created_at)
        result = await self.session.execute(query)
        return [self._map_to_domain(c) for c in result.scalars().all()]

    async def get_active(self) -> list[GroupChat]:
        query = select(OrmGroupChat).where(OrmGroupChat.status == "active")
        result = await self.session.execute(query)
        return [self._map_to_domain(c) for c in result.scalars().all()]

    async def get_pending_for_user(self, user_id: int) -> list[GroupChat]:
        query = select(OrmGroupChat).where(
            OrmGroupChat.status == "not_configured",
            OrmGroupChat.added_by_user_id == user_id,
        )
        result = await self.session.execute(query)
        return [self._map_to_domain(c) for c in result.scalars().all()]

    async def set_status(self, chat_id: int, status: str) -> GroupChat | None:
        return await self._update(chat_id, status=status)

    async def set_study_groups(
        self, chat_id: int, study_groups: list[int], configured_by_user_id: int
    ) -> GroupChat | None:
        return await self._update(
            chat_id,
            study_groups=study_groups,
            configured_by_user_id=configured_by_user_id,
            status="active",
        )

    async def set_pin_enabled(self, chat_id: int, enabled: bool) -> GroupChat | None:
        return await self._update(chat_id, pin_enabled=enabled)

    async def set_pinned_messages(self, chat_id: int, message_ids: list[int]) -> GroupChat | None:
        return await self._update(chat_id, pinned_message_ids=message_ids)

    async def update_chat_id(self, old_chat_id: int, new_chat_id: int) -> GroupChat | None:
        stmt = (
            update(OrmGroupChat)
            .where(OrmGroupChat.chat_id == old_chat_id)
            .values(chat_id=new_chat_id)
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

    async def _update(self, chat_id: int, **values: object) -> GroupChat | None:
        stmt = (
            update(OrmGroupChat)
            .where(OrmGroupChat.chat_id == chat_id)
            .values(**values)
            .returning(OrmGroupChat)
        )
        result = await self.session.execute(stmt)
        orm_chat = result.scalar_one_or_none()

        if not orm_chat:
            return None

        return self._map_to_domain(orm_chat)

    @staticmethod
    def _map_to_domain(orm_chat: OrmGroupChat) -> GroupChat:
        return GroupChat(
            chat_id=orm_chat.chat_id,
            title=orm_chat.title,
            status=orm_chat.status,
            study_groups=list(orm_chat.study_groups),
            pin_enabled=orm_chat.pin_enabled,
            pinned_message_ids=list(orm_chat.pinned_message_ids),
            added_by_user_id=orm_chat.added_by_user_id,
            configured_by_user_id=orm_chat.configured_by_user_id,
            created_at=orm_chat.created_at,
        )
