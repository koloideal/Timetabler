from sqlalchemy import literal, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from timetabler.domain.schemas import User
from timetabler.infrastructure.database.models import User as OrmUser


class UsersDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        query = select(OrmUser).where(OrmUser.user_id == user_id)
        result = await self.session.execute(query)
        orm_user = result.scalar_one_or_none()

        if orm_user:
            return self._map_to_domain(orm_user)

        return None

    async def create(self, user_id: int, username: str | None) -> User | None:
        new_orm_user = (
            insert(OrmUser)
            .values(user_id=user_id, username=username)
            .on_conflict_do_nothing(index_elements=["user_id"])
        )

        await self.session.execute(new_orm_user)
        await self.session.flush()

        orm_user = await self.session.scalar(select(OrmUser).where(OrmUser.user_id == user_id))
        if not orm_user:
            return None

        return self._map_to_domain(orm_user)

    async def get_by_username(self, username: str) -> User | None:
        query = select(OrmUser).where(OrmUser.username == username)
        result = await self.session.execute(query)
        orm_user = result.scalar_one_or_none()

        if orm_user:
            return self._map_to_domain(orm_user)

        return None

    async def get_all(self) -> list[User]:
        query = select(OrmUser)
        result = await self.session.execute(query)
        return [self._map_to_domain(u) for u in result.scalars().all()]

    async def get_subscribed_to_group(self, group: str) -> list[User]:
        query = select(OrmUser).where(OrmUser.groups.any(literal(group)))
        result = await self.session.execute(query)
        return [self._map_to_domain(u) for u in result.scalars().all()]

    async def update_groups(self, user_id: int, groups: list[str]) -> User | None:
        stmt = (
            update(OrmUser)
            .where(OrmUser.user_id == user_id)
            .values(groups=groups)
            .returning(OrmUser)
        )
        result = await self.session.execute(stmt)
        orm_user = result.scalar_one_or_none()

        if not orm_user:
            return None

        return self._map_to_domain(orm_user)

    async def update_username(self, user_id: int, username: str | None) -> User | None:
        stmt = (
            update(OrmUser)
            .where(OrmUser.user_id == user_id)
            .values(username=username)
            .returning(OrmUser)
        )
        result = await self.session.execute(stmt)
        orm_user = result.scalar_one_or_none()

        if not orm_user:
            return None

        return self._map_to_domain(orm_user)

    async def set_notifications(self, user_id: int, enabled: bool) -> User | None:
        stmt = (
            update(OrmUser)
            .where(OrmUser.user_id == user_id)
            .values(notifications_enabled=enabled)
            .returning(OrmUser)
        )
        result = await self.session.execute(stmt)
        orm_user = result.scalar_one_or_none()

        if not orm_user:
            return None

        return self._map_to_domain(orm_user)

    async def set_subgroup_mode(self, user_id: int, mode: str) -> User | None:
        stmt = (
            update(OrmUser)
            .where(OrmUser.user_id == user_id)
            .values(subgroup_mode=mode)
            .returning(OrmUser)
        )
        result = await self.session.execute(stmt)
        orm_user = result.scalar_one_or_none()

        if not orm_user:
            return None

        return self._map_to_domain(orm_user)

    async def set_pin_enabled(self, user_id: int, enabled: bool) -> User | None:
        stmt = (
            update(OrmUser)
            .where(OrmUser.user_id == user_id)
            .values(pin_enabled=enabled)
            .returning(OrmUser)
        )
        result = await self.session.execute(stmt)
        orm_user = result.scalar_one_or_none()
        if not orm_user:
            return None
        return self._map_to_domain(orm_user)

    async def set_pinned_messages(self, user_id: int, message_ids: list[int]) -> User | None:
        stmt = (
            update(OrmUser)
            .where(OrmUser.user_id == user_id)
            .values(pinned_message_ids=message_ids)
            .returning(OrmUser)
        )
        result = await self.session.execute(stmt)
        orm_user = result.scalar_one_or_none()
        if not orm_user:
            return None
        return self._map_to_domain(orm_user)

    async def set_main_group(self, user_id: int, group_id: int | None) -> User | None:
        stmt = (
            update(OrmUser)
            .where(OrmUser.user_id == user_id)
            .values(main_group=group_id)
            .returning(OrmUser)
        )
        result = await self.session.execute(stmt)
        orm_user = result.scalar_one_or_none()
        if not orm_user:
            return None
        return self._map_to_domain(orm_user)

    async def set_banned(self, user_id: int, is_banned: bool) -> User | None:
        stmt = (
            update(OrmUser)
            .where(OrmUser.user_id == user_id)
            .values(is_banned=is_banned)
            .returning(OrmUser)
        )
        result = await self.session.execute(stmt)
        orm_user = result.scalar_one_or_none()

        if not orm_user:
            return None

        return self._map_to_domain(orm_user)

    @staticmethod
    def _map_to_domain(orm_user: OrmUser) -> User:
        return User(
            user_id=orm_user.user_id,
            username=orm_user.username,
            is_banned=orm_user.is_banned,
            notifications_enabled=orm_user.notifications_enabled,
            groups=list(orm_user.groups),
            created_at=orm_user.created_at,
            subgroup_mode=orm_user.subgroup_mode,
            pin_enabled=orm_user.pin_enabled,
            pinned_message_ids=list(orm_user.pinned_message_ids),
            main_group=orm_user.main_group,
        )
