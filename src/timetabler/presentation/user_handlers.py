import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from dishka import FromDishka

from timetabler.application.services.bot import BotService
from timetabler.application.services.user import UserService

logger = logging.getLogger(__name__)

user_router = Router()


@user_router.message(Command("start"))
async def start(
    message: Message,
    user_service: FromDishka[UserService],
    bot_service: FromDishka[BotService],
) -> None:
    assert message.from_user is not None
    user, is_new = await user_service.get_or_create(message.from_user.id, message.from_user.username)
    if is_new:
        await bot_service.notify_new_user(user)
    await message.answer(
        "👋 Привет! Я <b>Timetabler</b> — рассылаю расписание подписчикам.\n\n"
        "<i>Выбор групп и подписки появятся позже.</i>"
    )
