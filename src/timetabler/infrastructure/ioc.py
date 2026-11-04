from typing import AsyncIterable

from aiogram import Bot
from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from timetabler.application.ports import CreatorNotifier, ScheduleParser, ScheduleSender
from timetabler.application.services.broadcast import BroadcastService
from timetabler.application.services.channel import ChannelService
from timetabler.application.services.detection import DetectionService
from timetabler.application.services.group_chat import GroupChatService
from timetabler.application.services.revision import RevisionService
from timetabler.application.services.settings import SettingsService
from timetabler.application.services.sheets import SheetsService
from timetabler.application.services.study_group import StudyGroupService
from timetabler.application.services.user import UserService
from timetabler.infrastructure.config.app import (
    AppConfig,
    RevisionsConfig,
    SheetsClientConfig,
    SheetsSettingsConfig,
)
from timetabler.infrastructure.config.models import Config
from timetabler.infrastructure.database.config import new_session_maker
from timetabler.infrastructure.database.dao import (
    ChannelsDAO,
    DeliveriesDAO,
    GroupChatsDAO,
    RevisionsDAO,
    SentMessagesDAO,
    SettingsDAO,
    SheetSourcesDAO,
    StudyGroupsDAO,
    UsersDAO,
)
from timetabler.infrastructure.parsing.grid_parser import GridScheduleParser
from timetabler.infrastructure.sheets import GoogleSheetsClient
from timetabler.presentation.telegram import TelegramNotifier, TelegramScheduleSender


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
    def get_channels_dao(self, session: AsyncSession) -> ChannelsDAO:
        return ChannelsDAO(session)

    @provide
    def get_group_chats_dao(self, session: AsyncSession) -> GroupChatsDAO:
        return GroupChatsDAO(session)

    @provide
    def get_study_groups_dao(self, session: AsyncSession) -> StudyGroupsDAO:
        return StudyGroupsDAO(session)

    @provide
    def get_revisions_dao(self, session: AsyncSession) -> RevisionsDAO:
        return RevisionsDAO(session)

    @provide
    def get_sent_messages_dao(self, session: AsyncSession) -> SentMessagesDAO:
        return SentMessagesDAO(session)

    @provide
    def get_deliveries_dao(self, session: AsyncSession) -> DeliveriesDAO:
        return DeliveriesDAO(session)

    @provide
    def get_sheet_sources_dao(self, session: AsyncSession) -> SheetSourcesDAO:
        return SheetSourcesDAO(session)

    @provide
    def get_settings_dao(self, session: AsyncSession) -> SettingsDAO:
        return SettingsDAO(session)


class ServicesProvider(Provider):
    scope = Scope.REQUEST

    @provide
    def get_user_service(self, users_dao: UsersDAO) -> UserService:
        return UserService(users_dao)

    @provide
    def get_channel_service(self, channels_dao: ChannelsDAO) -> ChannelService:
        return ChannelService(channels_dao)

    @provide
    def get_group_chat_service(self, group_chats_dao: GroupChatsDAO) -> GroupChatService:
        return GroupChatService(group_chats_dao)

    @provide
    def get_study_group_service(self, study_groups_dao: StudyGroupsDAO) -> StudyGroupService:
        return StudyGroupService(study_groups_dao)

    @provide
    def get_sheets_service(self, sheet_sources_dao: SheetSourcesDAO) -> SheetsService:
        return SheetsService(sheet_sources_dao)

    @provide
    def get_settings_service(
        self,
        settings_dao: SettingsDAO,
        settings_config: SheetsSettingsConfig,
    ) -> SettingsService:
        return SettingsService(settings_dao, settings_config)

    @provide
    def get_revision_service(
        self,
        revisions_dao: RevisionsDAO,
        study_groups_dao: StudyGroupsDAO,
    ) -> RevisionService:
        return RevisionService(revisions_dao, study_groups_dao)

    @provide
    def get_broadcast_service(
        self,
        sender: ScheduleSender,
        session: AsyncSession,
        session_maker: async_sessionmaker[AsyncSession],
        users_dao: UsersDAO,
        group_chats_dao: GroupChatsDAO,
        channels_dao: ChannelsDAO,
        study_groups_dao: StudyGroupsDAO,
        revisions_dao: RevisionsDAO,
        sent_messages_dao: SentMessagesDAO,
        deliveries_dao: DeliveriesDAO,
        notifier: CreatorNotifier,
        revisions_config: RevisionsConfig,
    ) -> BroadcastService:
        return BroadcastService(
            sender, session, session_maker, users_dao, group_chats_dao, channels_dao,
            study_groups_dao, revisions_dao, sent_messages_dao, deliveries_dao,
            notifier, revisions_config,
        )

    @provide
    def get_detection_service(
        self,
        sheets_client: GoogleSheetsClient,
        parser: ScheduleParser,
        settings_service: SettingsService,
        sheets_service: SheetsService,
        revision_service: RevisionService,
        broadcast_service: BroadcastService,
        notifier: CreatorNotifier,
        revisions_config: RevisionsConfig,
    ) -> DetectionService:
        return DetectionService(
            sheets_client, parser, settings_service, sheets_service,
            revision_service, broadcast_service, notifier, revisions_config,
        )


class SheetsProvider(Provider):
    scope = Scope.APP

    @provide
    def get_sheets_client(
        self, client_config: SheetsClientConfig, config: Config
    ) -> GoogleSheetsClient:
        return GoogleSheetsClient(client_config, config.google.credentials_path)


class ParsersProvider(Provider):
    scope = Scope.APP

    @provide
    def get_schedule_parser(self, app_config: AppConfig) -> ScheduleParser:
        return GridScheduleParser(app_config)


class PresentationProvider(Provider):
    scope = Scope.APP

    @provide
    def get_telegram_notifier(
        self, bot: Bot, config: Config, app_config: AppConfig
    ) -> TelegramNotifier:
        return TelegramNotifier(bot, config, app_config)

    @provide
    def get_creator_notifier(self, notifier: TelegramNotifier) -> CreatorNotifier:
        return notifier

    @provide
    def get_telegram_schedule_sender(
        self, bot: Bot, app_config: AppConfig
    ) -> TelegramScheduleSender:
        return TelegramScheduleSender(bot, app_config)

    @provide
    def get_schedule_sender(self, sender: TelegramScheduleSender) -> ScheduleSender:
        return sender


class AppConfigProvider(Provider):
    @provide(scope=Scope.APP)
    def get_app_config(self) -> AppConfig:
        return AppConfig()

    @provide(scope=Scope.APP)
    def get_sheets_client_config(self, app_config: AppConfig) -> SheetsClientConfig:
        return app_config.sheets_client

    @provide(scope=Scope.APP)
    def get_sheets_settings_config(self, app_config: AppConfig) -> SheetsSettingsConfig:
        return app_config.sheets_settings

    @provide(scope=Scope.APP)
    def get_revisions_config(self, app_config: AppConfig) -> RevisionsConfig:
        return app_config.revisions
