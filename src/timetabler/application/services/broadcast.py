import logging
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InputRichMessage

from timetabler.infrastructure.config.app import AppConfig
from timetabler.infrastructure.database.dao import (
    GroupChatsDAO,
    StudyGroupsDAO,
    TimetablesDAO,
    UsersDAO,
)
from timetabler.infrastructure.notifications.timetable_text import (
    build_broadcast_message,
    format_group_schedule,
)


@dataclass
class BroadcastReport:
    users_sent: int
    users_failed: int
    chats_sent: int
    chats_failed: int
    groups: int


@dataclass
class BroadcastPreview:
    markdown: str
    groups: int
    lessons: int


class BroadcastService:
    def __init__(
        self,
        bot: Bot,
        config: AppConfig,
        users_dao: UsersDAO,
        group_chats_dao: GroupChatsDAO,
        study_groups_dao: StudyGroupsDAO,
        timetables_dao: TimetablesDAO,
    ) -> None:
        self.bot = bot
        self.config = config
        self.users_dao = users_dao
        self.group_chats_dao = group_chats_dao
        self.study_groups_dao = study_groups_dao
        self.timetables_dao = timetables_dao
        self._logger = logging.getLogger(__name__)

    async def _group_parts(self, for_date: date) -> dict[int, str]:
        entries = await self.timetables_dao.get_entries(for_date)
        base_audiences = await self.timetables_dao.get_base_audiences(for_date)
        aliases = {
            g.group_id: g.alias for g in await self.study_groups_dao.get_all()
        }

        by_group: dict[int, list] = {}
        for entry in entries:
            by_group.setdefault(entry.group_id, []).append(entry)

        def label(group_id: int) -> str:
            alias = aliases.get(group_id)
            return f"{group_id} — {alias}" if alias else str(group_id)

        return {
            group_id: format_group_schedule(
                label(group_id), base_audiences.get(group_id), by_group[group_id], self.config
            )
            for group_id in sorted(by_group)
        }

    def _message_for(self, for_date: date, parts: dict[int, str], groups: Iterable[str]) -> str | None:
        selected = [parts[int(g)] for g in groups if g.isdigit() and int(g) in parts]
        if not selected:
            return None
        return build_broadcast_message(for_date, selected, self.config)

    async def _send_rich(self, chat_id: int, markdown: str) -> None:
        await self.bot.send_rich_message(
            chat_id=chat_id, rich_message=InputRichMessage(markdown=markdown)
        )

    async def build_preview(self, for_date: date) -> BroadcastPreview | None:
        entries = await self.timetables_dao.get_entries(for_date)
        if not entries:
            return None
        parts = await self._group_parts(for_date)
        return BroadcastPreview(
            markdown=build_broadcast_message(for_date, list(parts.values()), self.config),
            groups=len(parts),
            lessons=len(entries),
        )

    async def broadcast(self, for_date: date) -> BroadcastReport:
        parts = await self._group_parts(for_date)
        report = BroadcastReport(0, 0, 0, 0, len(parts))

        for user in await self.users_dao.get_all():
            if user.is_banned or not user.notifications_enabled:
                continue
            markdown = self._message_for(for_date, parts, user.groups)
            if markdown is None:
                continue
            try:
                await self._send_rich(user.user_id, markdown)
                report.users_sent += 1
            except TelegramForbiddenError:
                report.users_failed += 1

        for chat in await self.group_chats_dao.get_all():
            markdown = self._message_for(for_date, parts, chat.groups)
            if markdown is None:
                continue
            try:
                await self._send_rich(chat.chat_id, markdown)
                report.chats_sent += 1
            except TelegramForbiddenError:
                report.chats_failed += 1

        self._logger.info(
            "Broadcast %s: %s users, %s chats, %s groups",
            for_date, report.users_sent, report.chats_sent, report.groups,
        )
        return report
