from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from timetabler.infrastructure.config.models import Config


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
