import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from timetabler.domain.schemas import User
from timetabler.infrastructure.config.models import Config
from timetabler.infrastructure.database.dao import UsersDAO

logger = logging.getLogger(__name__)


class BotService:
    def __init__(self, bot: Bot, config: Config, users_dao: UsersDAO) -> None:
        self.bot = bot
        self.config = config
        self.users_dao = users_dao

    async def process_set_commands(self) -> None:
        user_commands = [
            BotCommand(command="start", description="🚀 Начало работы"),
            BotCommand(command="help", description="ℹ️ Справка"),
        ]

        staff_commands = user_commands + [
            BotCommand(command="admin", description="🛠 Админ-панель"),
        ]

        await self.bot.set_my_commands(
            commands=user_commands,
            scope=BotCommandScopeDefault(),
        )

        await self.bot.set_my_commands(
            commands=staff_commands,
            scope=BotCommandScopeChat(chat_id=self.config.bot.creator_id),
        )

        for admin in await self.users_dao.get_admins():
            try:
                await self.bot.set_my_commands(
                    commands=user_commands,
                    scope=BotCommandScopeChat(chat_id=admin.user_id),
                )
            except TelegramForbiddenError:
                logger.warning("Cannot set commands for admin %s: bot is blocked", admin.user_id)

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
                "⭐ Вам выданы права администратора.\n"
                "Теперь вы можете загружать расписание — просто отправьте файл .xlsx или .csv.",
            )
        except TelegramForbiddenError:
            logger.warning("Cannot notify new admin %s: bot is blocked", user_id)
