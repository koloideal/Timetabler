from time import monotonic
from typing import Awaitable, Callable, cast

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from dishka import AsyncContainer

from timetabler.application.services.user import UserService


class CheckBanMiddleware(BaseMiddleware):
    _TTL_SECONDS = 60

    def __init__(self) -> None:
        self._cache: dict[int, tuple[bool, float]] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, object]], Awaitable[object]],
        event: TelegramObject,
        data: dict[str, object],
    ) -> object | None:
        update = event

        if not update or not isinstance(update, Update):
            return await handler(event, data)

        user_id = None

        if update.message and update.message.from_user:
            user_id = update.message.from_user.id
        elif update.callback_query and update.callback_query.from_user:
            user_id = update.callback_query.from_user.id

        if not user_id:
            return await handler(event, data)

        cached = self._cache.get(user_id)
        if cached is not None and cached[1] > monotonic():
            banned = cached[0]
        else:
            container = cast(AsyncContainer, data["dishka_container"])
            user_service: UserService = await container.get(UserService)
            banned = await user_service.is_banned(user_id)
            self._cache[user_id] = (banned, monotonic() + self._TTL_SECONDS)

        if banned:
            message_text = "🔒 Вы заблокированы"

            if update.message:
                await update.message.answer(message_text)
            elif update.callback_query:
                await update.callback_query.answer(message_text, show_alert=True)

            return None

        return await handler(event, data)
