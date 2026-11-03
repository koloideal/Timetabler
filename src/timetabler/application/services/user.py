from timetabler.domain.schemas import User
from timetabler.infrastructure.database.dao import UsersDAO


class UserService:
    def __init__(self, users_dao: UsersDAO) -> None:
        self.users_dao = users_dao

    async def get_or_create(self, user_id: int, username: str | None) -> User:
        user = await self.users_dao.get_by_id(user_id)
        if user is None:
            user = await self.users_dao.create(user_id, username)

        assert user is not None
        return user

    async def is_banned(self, user_id: int) -> bool:
        user = await self.users_dao.get_by_id(user_id)
        return user.is_banned if user else False

    async def is_admin(self, user_id: int) -> bool:
        user = await self.users_dao.get_by_id(user_id)
        return user.is_admin if user else False
