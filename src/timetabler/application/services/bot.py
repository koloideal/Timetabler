import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    InlineKeyboardMarkup,
)

from timetabler.domain.schemas import User
from timetabler.infrastructure.config.models import Config
from timetabler.infrastructure.database.dao import UsersDAO

class BotService:
    def __init__(self, bot: Bot, config: Config, users_dao: UsersDAO) -> None:
        self.bot = bot
        self.config = config
        self.users_dao = users_dao
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

    async def notify_new_user(self, user: User) -> None:
        username = f"@{user.username}" if user.username else "—"
        await self.notify_creator(
            f"🆕 <b>НОВЫЙ ЮЗЕР</b>\n<pre>USERNAME  {username}\nID        {user.user_id}</pre>"
        )
