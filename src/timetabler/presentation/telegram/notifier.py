import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    InlineKeyboardMarkup,
    InputRichBlockUnion,
    InputRichMessage,
)

from timetabler.application.ports import CreatorNotifier
from timetabler.domain.schemas import Revision, User
from timetabler.infrastructure.config.app import AppConfig
from timetabler.infrastructure.config.models import Config
from timetabler.presentation.messages import (
    new_user_text,
    revision_approval_markup,
    revision_approval_text,
)


class TelegramNotifier(CreatorNotifier):
    def __init__(self, bot: Bot, config: Config, app_config: AppConfig) -> None:
        self.bot = bot
        self.config = config
        self.app_config = app_config
        self._logger = logging.getLogger(__name__)

    async def process_set_commands(self) -> None:
        user_commands = [
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="help", description="Справка"),
        ]

        creator_commands = user_commands + [
            BotCommand(command="admin", description="Админ-панель"),
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
        self,
        chat_id: int,
        content: str | list[InputRichBlockUnion],
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        rich_message = (
            InputRichMessage(markdown=content)
            if isinstance(content, str)
            else InputRichMessage(blocks=content)
        )
        await self.bot.send_rich_message(
            chat_id=chat_id,
            rich_message=rich_message,
            reply_markup=reply_markup,
        )

    async def send_rich_to_creator(
        self,
        content: str | list[InputRichBlockUnion],
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        await self.send_rich_message(self.config.bot.creator_id, content, reply_markup)

    async def ask_revision_approval(self, revision: Revision) -> None:
        await self.send_rich_to_creator(
            revision_approval_text(revision, self.app_config),
            reply_markup=revision_approval_markup(revision.id),
        )

    async def notify_new_user(self, user: User) -> None:
        await self.notify_creator(new_user_text(user))
