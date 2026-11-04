import logging
from datetime import date

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramMigrateToChat,
)
from aiogram.types import InputRichMessage

from timetabler.application.ports import ChatDelivery, ScheduleSender
from timetabler.domain.schemas import DaySchedule
from timetabler.infrastructure.config.app import AppConfig
from timetabler.presentation.messages import channel_html, group_content


class TelegramScheduleSender(ScheduleSender):
    def __init__(self, bot: Bot, app_config: AppConfig) -> None:
        self.bot = bot
        self.config = app_config
        self._logger = logging.getLogger(__name__)

    @staticmethod
    def _with_note(markdown: str, note: str | None) -> str:
        return f"{markdown}\n\n---\n\n🔄 *{note}*" if note else markdown

    @staticmethod
    def _with_note_html(html: str, note: str | None) -> str:
        return f"{html}<p>🔄 <i>{note}</i></p>" if note else html

    async def send_group_schedule(
        self, chat_id: int, for_date: date, day: DaySchedule, group_id: int,
        note: str | None = None, mode: str = "a",
    ) -> int | None:
        content = group_content(day, for_date, group_id, mode, self.config)
        if content is None:
            return None
        markdown, markup = content
        try:
            message = await self.bot.send_rich_message(
                chat_id=chat_id,
                rich_message=InputRichMessage(markdown=self._with_note(markdown, note)),
                reply_markup=markup,
            )
            return message.message_id
        except TelegramForbiddenError:
            return None

    async def send_channel_schedule(
        self, chat_id: int, for_date: date, day: DaySchedule, note: str | None = None
    ) -> int | None:
        if not day.by_group:
            return None
        try:
            message = await self.bot.send_rich_message(
                chat_id=chat_id,
                rich_message=InputRichMessage(
                    html=self._with_note_html(channel_html(day, for_date, self.config), note)
                ),
            )
            return message.message_id
        except TelegramForbiddenError:
            return None

    async def edit_channel_schedule(
        self, chat_id: int, message_id: int, for_date: date, day: DaySchedule,
        note: str | None = None,
    ) -> bool:
        if not day.by_group:
            return False
        try:
            await self.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                rich_message=InputRichMessage(
                    html=self._with_note_html(channel_html(day, for_date, self.config), note)
                ),
            )
            return True
        except TelegramAPIError:
            return False

    async def send_chat_schedule(
        self, chat_id: int, for_date: date, day: DaySchedule, group_id: int,
        note: str | None = None,
    ) -> ChatDelivery:
        content = group_content(day, for_date, group_id, "a", self.config)
        if content is None:
            return ChatDelivery()
        markdown, _ = content
        try:
            message = await self.bot.send_rich_message(
                chat_id=chat_id,
                rich_message=InputRichMessage(markdown=self._with_note(markdown, note)),
            )
            return ChatDelivery(message_id=message.message_id)
        except TelegramMigrateToChat as e:
            return ChatDelivery(migrate_to=e.migrate_to_chat_id)
        except (TelegramForbiddenError, TelegramBadRequest):
            return ChatDelivery(failed=True)

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        try:
            await self.bot.delete_message(chat_id, message_id)
        except TelegramAPIError:
            pass

    async def pin_chat_message(self, chat_id: int, message_id: int) -> bool:
        try:
            return await self.bot.pin_chat_message(
                chat_id, message_id, disable_notification=True
            )
        except TelegramAPIError:
            return False

    async def unpin_chat_message(self, chat_id: int, message_id: int) -> None:
        try:
            await self.bot.unpin_chat_message(chat_id, message_id=message_id)
        except TelegramAPIError:
            pass

    async def send_text(self, chat_id: int, text: str) -> bool:
        try:
            await self.bot.send_message(chat_id, text)
            return True
        except TelegramAPIError:
            return False
