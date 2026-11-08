from datetime import date

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from timetabler.domain.schemas import SentMessage
from timetabler.infrastructure.database.models import SentMessage as OrmSentMessage


class SentMessagesDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_day(self, chat_id: int, for_date: date) -> list[SentMessage]:
        query = (
            select(OrmSentMessage)
            .where(
                OrmSentMessage.chat_id == chat_id,
                OrmSentMessage.for_date == for_date,
            )
            .order_by(OrmSentMessage.id)
        )
        result = await self.session.execute(query)
        return [self._map_to_domain(m) for m in result.scalars().all()]

    async def get_for_user_group(
        self, chat_id: int, group: str
    ) -> list[SentMessage]:
        query = select(OrmSentMessage).where(
            OrmSentMessage.chat_id == chat_id,
            OrmSentMessage.groups.contains([group]),
        )
        result = await self.session.execute(query)
        return [self._map_to_domain(m) for m in result.scalars().all()]

    async def get_for_revision(self, revision_id: int, chat_id: int) -> list[SentMessage]:
        query = select(OrmSentMessage).where(
            OrmSentMessage.revision_id == revision_id,
            OrmSentMessage.chat_id == chat_id,
        )
        result = await self.session.execute(query)
        return [self._map_to_domain(m) for m in result.scalars().all()]

    async def add(
        self,
        revision_id: int | None,
        for_date: date,
        chat_id: int,
        message_id: int,
        kind: str,
        groups: list[str],
    ) -> SentMessage:
        orm_message = OrmSentMessage(
            revision_id=revision_id,
            for_date=for_date,
            chat_id=chat_id,
            message_id=message_id,
            kind=kind,
            groups=groups,
        )
        self.session.add(orm_message)
        await self.session.flush()
        return self._map_to_domain(orm_message)

    async def set_revision(self, row_id: int, revision_id: int) -> None:
        stmt = (
            update(OrmSentMessage)
            .where(OrmSentMessage.id == row_id)
            .values(revision_id=revision_id, sent_at=func.now())
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def remove(self, row_id: int) -> None:
        await self.session.execute(
            delete(OrmSentMessage).where(OrmSentMessage.id == row_id)
        )
        await self.session.flush()

    @staticmethod
    def _map_to_domain(orm_message: OrmSentMessage) -> SentMessage:
        return SentMessage(
            id=orm_message.id,
            revision_id=orm_message.revision_id,
            for_date=orm_message.for_date,
            chat_id=orm_message.chat_id,
            message_id=orm_message.message_id,
            kind=orm_message.kind,
            groups=list(orm_message.groups),
            sent_at=orm_message.sent_at,
        )
