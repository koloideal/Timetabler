from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram_dialog import DialogManager, StartMode
from dishka import FromDishka

from timetabler.application.services.bot import BotService
from timetabler.application.services.user import UserService
from timetabler.infrastructure.config.app import AppConfig
from timetabler.infrastructure.config.models import Config
from timetabler.presentation.user_dialogs import UserMenuSG


def new_user_router() -> Router:
    router = Router()

    @router.message(Command("start"))
    async def start(
        message: Message,
        dialog_manager: DialogManager,
        user_service: FromDishka[UserService],
        bot_service: FromDishka[BotService],
    ) -> None:
        assert message.from_user is not None
        user, is_new = await user_service.get_or_create(message.from_user.id, message.from_user.username)
        if is_new:
            await bot_service.notify_new_user(user)
        await dialog_manager.start(UserMenuSG.main, mode=StartMode.RESET_STACK)

    @router.message(Command("help"))
    async def help_handler(
        message: Message,
        config: FromDishka[Config],
        app_config: FromDishka[AppConfig],
    ) -> None:
        assert message.from_user is not None
        if message.from_user.id == config.bot.creator_id:
            await message.answer(app_config.creator_help)
        else:
            await message.answer(app_config.user_help)

    return router
