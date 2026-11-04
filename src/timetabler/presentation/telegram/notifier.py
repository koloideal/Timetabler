import logging
from datetime import date

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    InlineKeyboardMarkup,
    InputRichMessage,
)

from timetabler.application.ports import CreatorNotifier
from timetabler.domain.schemas import BroadcastSummary, DaySchedule, User
from timetabler.infrastructure.config.app import AppConfig
from timetabler.infrastructure.config.models import Config
from timetabler.presentation.messages import (
    broadcast_confirmation_markup,
    new_user_text,
    preview,
    schedule_updated_text,
)


class TelegramNotifier(CreatorNotifier):
    def __init__(self, bot: Bot, config: Config, app_config: AppConfig) -> None:
        self.bot = bot
        self.config = config
        self.app_config = app_config
        self._logger = logging.getLogger(__name__)

    async def process_set_commands(self) -> None:
        user_commands = [
            BotCommand(command="start", description="🚀 Начало работы"),
            BotCommand(command="help", description="ℹ️ Справка"),
        ]

        creator_commands = user_commands + [
            BotCommand(command="admin", description="🛠 Панель создателя"),
        ]

        await self.bot.set_my_commands(
            commands=user_commands,
            scope=BotCommandScopeDefault(),
        )

        await self.bot.set_my_commands(
            commands=creator_commands,
            scope=BotCommandScopeChat(chat_id=self.config.bot.creator_id),
        )

    async def notify_creator(self, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
        try:
            await self.bot.send_message(self.config.bot.creator_id, text, reply_markup=reply_markup)
        except TelegramForbiddenError:
            self._logger.warning("Cannot notify creator %s: bot is blocked", self.config.bot.creator_id)

    async def send_rich_message(
        self, chat_id: int, markdown: str, reply_markup: InlineKeyboardMarkup | None = None
    ) -> None:
        await self.bot.send_rich_message(
            chat_id=chat_id,
            rich_message=InputRichMessage(markdown=markdown),
            reply_markup=reply_markup,
        )

    async def send_rich_to_creator(
        self, markdown: str, reply_markup: InlineKeyboardMarkup | None = None
    ) -> None:
        await self.send_rich_message(self.config.bot.creator_id, markdown, reply_markup)

    async def ask_broadcast_confirmation(self, for_date: date, day: DaySchedule) -> None:
        schedule_preview = preview(day, for_date, self.app_config)
        markdown = schedule_preview.markdown if schedule_preview else "📅 Новое расписание"
        await self.send_rich_to_creator(
            f"{markdown}\n\n---\n\n**Подтвердить рассылку подписчикам?**",
            reply_markup=broadcast_confirmation_markup(),
        )

    async def notify_schedule_updated(self, summary: BroadcastSummary) -> None:
        await self.notify_creator(schedule_updated_text(summary, self.app_config))

    async def notify_new_user(self, user: User) -> None:
        await self.notify_creator(new_user_text(user))
