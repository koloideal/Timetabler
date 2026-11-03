import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from dishka import FromDishka

from timetabler.application.services.user import UserService

logger = logging.getLogger(__name__)

user_router = Router()


@user_router.message(Command("start"))
async def start(message: Message, user_service: FromDishka[UserService]) -> None:
    assert message.from_user is not None
    await user_service.get_or_create(message.from_user.id, message.from_user.username)
    await message.answer(
        "👋 Привет! Я <b>Timetabler</b> — рассылаю расписание подписчикам.\n\n"
        "<i>Выбор групп и подписки появятся позже.</i>"
    )
