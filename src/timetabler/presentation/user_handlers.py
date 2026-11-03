import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from dishka import FromDishka

from timetabler.application.services.bot import BotService
from timetabler.application.services.user import UserService
from timetabler.infrastructure.config.app import AppConfig
from timetabler.infrastructure.config.models import Config

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
        "Справка: /help"
    )


@user_router.message(Command("help"))
async def help_handler(
    message: Message,
    user_service: FromDishka[UserService],
    config: FromDishka[Config],
    app_config: FromDishka[AppConfig],
) -> None:
    assert message.from_user is not None
    user_id = message.from_user.id
    if user_id == config.bot.creator_id:
        await message.answer(app_config.staff_help + app_config.creator_help_extra)
    elif await user_service.is_admin(user_id):
        await message.answer(app_config.staff_help)
    else:
        await message.answer(app_config.user_help)
