import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

logger = logging.getLogger(__name__)

admin_router = Router()


@admin_router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    await message.answer("🛠 Админ-панель. <i>Заглушка.</i>")
