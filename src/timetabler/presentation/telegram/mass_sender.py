import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramMigrateToChat,
    TelegramRetryAfter,
)

from timetabler.application.ports import MassSender
from timetabler.application.ports.mass_sender import COPY_BLOCKED, COPY_FAILED, COPY_OK
from timetabler.infrastructure.config.app import MassBroadcastConfig


class TelegramMassSender(MassSender):
    def __init__(self, bot: Bot, config: MassBroadcastConfig) -> None:
        self.bot = bot
        self.config = config
        self._logger = logging.getLogger(__name__)

    async def copy_to(self, chat_id: int, from_chat_id: int, message_id: int) -> str:
        target = chat_id
        for _ in range(self.config.max_retry_attempts):
            try:
                await self.bot.copy_message(target, from_chat_id, message_id)
                return COPY_OK
            except TelegramRetryAfter as e:
                wait = min(e.retry_after + 1, self.config.max_retry_wait_seconds)
                self._logger.warning("Mass broadcast flood control, waiting %ss", wait)
                await asyncio.sleep(wait)
            except TelegramMigrateToChat as e:
                target = e.migrate_to_chat_id
            except TelegramForbiddenError:
                return COPY_BLOCKED
            except TelegramBadRequest as e:
                self._logger.warning("Mass copy to %s failed: %s", target, e.message)
                return COPY_FAILED
            except TelegramAPIError as e:
                self._logger.warning("Mass copy to %s failed: %s", target, e.message)
                return COPY_FAILED
        return COPY_FAILED
