from timetabler.domain.schemas import User
from timetabler.infrastructure.database.dao import UsersDAO


class UserService:
    def __init__(self, users_dao: UsersDAO) -> None:
        self.users_dao = users_dao

    async def get_or_create(self, user_id: int, username: str | None) -> tuple[User, bool]:
        user = await self.users_dao.get_by_id(user_id)
        if user is not None:
            if username is not None and user.username != username:
                user = await self.users_dao.update_username(user_id, username)
            assert user is not None
            return user, False

        user = await self.users_dao.create(user_id, username)
        assert user is not None
        return user, True

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.users_dao.get_by_id(user_id)

    async def get_by_username(self, username: str) -> User | None:
        return await self.users_dao.get_by_username(username)

    async def list_users(self) -> list[User]:
        return await self.users_dao.get_all()

    async def set_group_membership(
        self, user_id: int, group_id: int, subscribed: bool
    ) -> User | None:
        user = await self.users_dao.get_by_id(user_id)
        if user is None:
            return None
        groups = set(user.groups)
        groups.discard(str(group_id))
        if subscribed:
            groups.add(str(group_id))
        return await self.users_dao.update_groups(user_id, sorted(groups))

    async def set_main_group(self, user_id: int, group_id: int | None) -> User | None:
        user = await self.users_dao.get_by_id(user_id)
        if user is None:
            return None
        if group_id is not None and str(group_id) not in user.groups:
            groups = sorted({*user.groups, str(group_id)})
            await self.users_dao.update_groups(user_id, groups)
        return await self.users_dao.set_main_group(user_id, group_id)

    async def set_notifications(self, user_id: int, enabled: bool) -> User | None:
        return await self.users_dao.set_notifications(user_id, enabled)

    async def set_subgroup_mode(self, user_id: int, mode: str) -> User | None:
        if mode not in {"a", "1", "2"}:
            return None
        return await self.users_dao.set_subgroup_mode(user_id, mode)

    async def set_pin(self, user_id: int, enabled: bool) -> User | None:
        return await self.users_dao.set_pin_enabled(user_id, enabled)

    async def set_pinned_messages(
        self, user_id: int, message_ids: list[int]
    ) -> User | None:
        return await self.users_dao.set_pinned_messages(user_id, message_ids)

    async def is_banned(self, user_id: int) -> bool:
        user = await self.users_dao.get_by_id(user_id)
        return user.is_banned if user else False

    async def set_banned(self, user_id: int, is_banned: bool) -> User | None:
        return await self.users_dao.set_banned(user_id, is_banned)
