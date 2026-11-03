from typing import AsyncIterable

from aiogram import Bot
from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from timetabler.application.services.bot import BotService
from timetabler.application.services.group_chat import GroupChatService
from timetabler.application.services.study_group import StudyGroupService
from timetabler.application.services.timetable import TimetableService
from timetabler.application.ports import TimetableParser
from timetabler.application.services.user import UserService
from timetabler.infrastructure.config.app import AppConfig
from timetabler.infrastructure.config.models import Config
from timetabler.infrastructure.database.config import new_session_maker
from timetabler.infrastructure.database.dao import (
    GroupChatsDAO,
    StudyGroupsDAO,
    TimetableEntriesDAO,
    UsersDAO,
)
from timetabler.infrastructure.parsing.csv_parser import CsvTimetableParser
from timetabler.infrastructure.parsing.xlsx_parser import XlsxTimetableParser


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

    @provide
    def get_study_groups_dao(self, session: AsyncSession) -> StudyGroupsDAO:
        return StudyGroupsDAO(session)

    @provide
    def get_timetable_entries_dao(self, session: AsyncSession) -> TimetableEntriesDAO:
        return TimetableEntriesDAO(session)


class ServicesProvider(Provider):
    scope = Scope.REQUEST

    @provide
    def get_user_service(self, users_dao: UsersDAO) -> UserService:
        return UserService(users_dao)

    @provide
    def get_bot_service(self, bot: Bot, config: Config, users_dao: UsersDAO) -> BotService:
        return BotService(bot, config, users_dao)

    @provide
    def get_group_chat_service(self, group_chats_dao: GroupChatsDAO) -> GroupChatService:
        return GroupChatService(group_chats_dao)

    @provide
    def get_study_group_service(self, study_groups_dao: StudyGroupsDAO) -> StudyGroupService:
        return StudyGroupService(study_groups_dao)

    @provide
    def get_timetable_service(
        self,
        timetable_entries_dao: TimetableEntriesDAO,
        study_group_service: StudyGroupService,
        parsers: dict[str, TimetableParser],
    ) -> TimetableService:
        return TimetableService(timetable_entries_dao, study_group_service, parsers)


class ParsersProvider(Provider):
    scope = Scope.APP

    @provide
    def get_timetable_parsers(self, app_config: AppConfig) -> dict[str, TimetableParser]:
        return {
            ".xlsx": XlsxTimetableParser(app_config),
            ".csv": CsvTimetableParser(app_config),
        }


class AppConfigProvider(Provider):
    @provide(scope=Scope.APP)
    def get_app_config(self) -> AppConfig:
        return AppConfig()
