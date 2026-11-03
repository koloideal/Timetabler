from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
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
        if isinstance(event, Message):
            if not event.text or event.text.strip() != "/admin":
                return await handler(event, data)
        elif not isinstance(event, CallbackQuery):
            return await handler(event, data)

        user = event.from_user
        if user is None:
            return await handler(event, data)

        container: AsyncContainer = data["dishka_container"]
        config: Config = await container.get(Config)
        user_service: UserService = await container.get(UserService)

        if user.id == config.bot.creator_id or await user_service.is_admin(user.id):
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await event.answer("⛔ Нет доступа", show_alert=True)
