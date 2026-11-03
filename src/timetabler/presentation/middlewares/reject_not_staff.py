from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from dishka import AsyncContainer

from timetabler.application.services.user import UserService
from timetabler.infrastructure.config.models import Config


class RejectNotStaffMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, (Message, CallbackQuery)) or event.from_user is None:
            return await handler(event, data)

        container: AsyncContainer = data["dishka_container"]
        config: Config = await container.get(Config)
        user_service: UserService = await container.get(UserService)

        user_id = event.from_user.id
        if user_id == config.bot.creator_id or await user_service.is_admin(user_id):
            return await handler(event, data)
