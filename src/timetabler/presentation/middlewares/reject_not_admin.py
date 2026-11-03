from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from dishka import AsyncContainer

from timetabler.application.services.user import UserService
from timetabler.infrastructure.config.models import Config


class RejectNotAdminMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not event.text:
            return await handler(event, data)

        container: AsyncContainer = data["dishka_container"]
        config: Config = await container.get(Config)
        user_service: UserService = await container.get(UserService)

        assert event.from_user is not None
        if event.from_user.id == config.bot.creator_id or await user_service.is_admin(event.from_user.id):
            return await handler(event, data)
