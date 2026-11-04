from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from timetabler.domain.schemas import Delivery
from timetabler.infrastructure.database.models import Delivery as OrmDelivery


class DeliveriesDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure(self, revision_id: int, recipients: list[tuple[str, int]]) -> None:
        if not recipients:
            return
        stmt = (
            insert(OrmDelivery)
            .values(
                [
                    {"revision_id": revision_id, "kind": kind, "chat_id": chat_id}
                    for kind, chat_id in recipients
                ]
            )
            .on_conflict_do_nothing(
                index_elements=["revision_id", "kind", "chat_id"]
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def get_pending(self, revision_id: int) -> list[Delivery]:
        query = (
            select(OrmDelivery)
            .where(
                OrmDelivery.revision_id == revision_id,
                OrmDelivery.status == "pending",
            )
            .order_by(OrmDelivery.id)
        )
        result = await self.session.execute(query)
        return [self._map_to_domain(d) for d in result.scalars().all()]

    async def set_status(self, delivery_id: int, status: str) -> None:
        stmt = (
            update(OrmDelivery)
            .where(OrmDelivery.id == delivery_id)
            .values(status=status, sent_at=func.now())
        )
        await self.session.execute(stmt)
        await self.session.flush()

    @staticmethod
    def _map_to_domain(orm_delivery: OrmDelivery) -> Delivery:
        return Delivery(
            id=orm_delivery.id,
            revision_id=orm_delivery.revision_id,
            kind=orm_delivery.kind,
            chat_id=orm_delivery.chat_id,
            status=orm_delivery.status,
            sent_at=orm_delivery.sent_at,
        )
