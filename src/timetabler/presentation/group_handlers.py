import logging

from aiogram import F, Router
from aiogram.enums.chat_type import ChatType
from aiogram.filters import Command
from aiogram.types import Message

logger = logging.getLogger(__name__)

group_router = Router()
group_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))


@group_router.message(Command("start"))
async def group_start(message: Message) -> None:
    await message.answer(
        "👋 Привет! Я буду присылать расписание в этот чат.\n\n"
        "<i>Настройка групп появится позже.</i>"
    )
