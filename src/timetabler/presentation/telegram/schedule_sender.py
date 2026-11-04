import logging
from datetime import date

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InputRichMessage

from timetabler.application.ports import ScheduleSender
from timetabler.domain.schemas import DaySchedule
from timetabler.infrastructure.config.app import AppConfig
from timetabler.presentation.messages import channel_html, group_content


class TelegramScheduleSender(ScheduleSender):
    def __init__(self, bot: Bot, app_config: AppConfig) -> None:
        self.bot = bot
        self.config = app_config
        self._logger = logging.getLogger(__name__)

    async def send_group_schedule(
        self, chat_id: int, for_date: date, day: DaySchedule, group_id: int
    ) -> bool:
        content = group_content(day, for_date, group_id, "a", self.config)
        if content is None:
            return False
        markdown, markup = content
        try:
            await self.bot.send_rich_message(
                chat_id=chat_id,
                rich_message=InputRichMessage(markdown=markdown),
                reply_markup=markup,
            )
            return True
        except TelegramForbiddenError:
            return False

    async def send_channel_schedule(
        self, chat_id: int, for_date: date, day: DaySchedule
    ) -> bool:
        if not day.by_group:
            return False
        try:
            await self.bot.send_rich_message(
                chat_id=chat_id,
                rich_message=InputRichMessage(html=channel_html(day, for_date, self.config)),
            )
            return True
        except TelegramForbiddenError:
            return False
