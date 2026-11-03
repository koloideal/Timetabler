import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from timetabler.domain.schemas import User
from timetabler.infrastructure.config.models import Config

logger = logging.getLogger(__name__)


class BotService:
    def __init__(self, bot: Bot, config: Config) -> None:
        self.bot = bot
        self.config = config

    async def process_set_commands(self) -> None:
        user_commands = [
            BotCommand(command="start", description="🚀 Начало работы"),
        ]

        admin_commands = user_commands + [
            BotCommand(command="admin", description="🛠 Админ-панель"),
        ]

        await self.bot.set_my_commands(
            commands=user_commands,
            scope=BotCommandScopeDefault(),
        )

        await self.bot.set_my_commands(
            commands=admin_commands,
            scope=BotCommandScopeChat(chat_id=self.config.bot.creator_id),
        )

    async def notify_creator(self, text: str) -> None:
        try:
            await self.bot.send_message(self.config.bot.creator_id, text)
        except TelegramForbiddenError:
            logger.warning("Cannot notify creator %s: bot is blocked", self.config.bot.creator_id)

    async def notify_new_user(self, user: User) -> None:
        username = f"@{user.username}" if user.username else "—"
        await self.notify_creator(
            f"🆕 Новый юзер\n<blockquote>• Username: {username}\n• ID: <code>{user.user_id}</code></blockquote>"
        )

    async def notify_admin_assigned(self, user_id: int) -> None:
        try:
            await self.bot.send_message(
                user_id,
                "⭐ Вам выданы права администратора.\nОткройте панель: /admin",
            )
        except TelegramForbiddenError:
            logger.warning("Cannot notify new admin %s: bot is blocked", user_id)
