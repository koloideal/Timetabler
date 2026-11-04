from typing import Awaitable, Callable, cast

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from dishka import AsyncContainer

from timetabler.infrastructure.config.models import Config


class RejectNotCreatorMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, object]], Awaitable[object]],
        event: TelegramObject,
        data: dict[str, object],
    ) -> object | None:
        if isinstance(event, Message):
            if not event.text or event.text.strip() != "/admin":
                return await handler(event, data)
        elif not isinstance(event, CallbackQuery):
            return await handler(event, data)

        user = event.from_user
        if user is None:
            return await handler(event, data)

        container = cast(AsyncContainer, data["dishka_container"])
        config: Config = await container.get(Config)

        if user.id == config.bot.creator_id:
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await event.answer("⛔ Нет доступа", show_alert=True)
        elif isinstance(event, Message):
            await event.answer("⛔ Нет доступа")
        return None
