from typing import AsyncIterable

from aiogram import Bot
from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from timetabler.application.services.bot import BotService
from timetabler.application.services.group_chat import GroupChatService
from timetabler.application.services.user import UserService
from timetabler.infrastructure.config.models import Config
from timetabler.infrastructure.database.config import new_session_maker
from timetabler.infrastructure.database.dao import GroupChatsDAO, UsersDAO


class DatabaseProvider(Provider):
    scope = Scope.REQUEST

    @provide(scope=Scope.APP)
    def get_session_maker(self, config: Config) -> async_sessionmaker[AsyncSession]:
        return new_session_maker(config.postgres.dsn)

    @provide
    async def get_session(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> AsyncIterable[AsyncSession]:
        async with session_maker() as session:
            async with session.begin():
                yield session

    @provide
    def get_users_dao(self, session: AsyncSession) -> UsersDAO:
        return UsersDAO(session)

    @provide
    def get_group_chats_dao(self, session: AsyncSession) -> GroupChatsDAO:
        return GroupChatsDAO(session)


class ServicesProvider(Provider):
    scope = Scope.REQUEST

    @provide
    def get_user_service(self, users_dao: UsersDAO) -> UserService:
        return UserService(users_dao)

    @provide
    def get_bot_service(self, bot: Bot, config: Config) -> BotService:
        return BotService(bot, config)

    @provide
    def get_group_chat_service(self, group_chats_dao: GroupChatsDAO) -> GroupChatService:
        return GroupChatService(group_chats_dao)
