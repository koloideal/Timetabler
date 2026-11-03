from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from dishka import AsyncContainer

from timetabler.application.services.user import UserService


class CheckBanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
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

        container: AsyncContainer = data["dishka_container"]
        user_service: UserService = await container.get(UserService)

        if await user_service.is_banned(user_id):
            message_text = "🚫 Вы заблокированы."

            if update.message:
                await update.message.answer(message_text)
            elif update.callback_query:
                await update.callback_query.answer(message_text, show_alert=True)

            return

        return await handler(event, data)
