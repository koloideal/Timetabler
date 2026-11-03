import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup, InputRichMessage

from timetabler.domain.schemas import TimetableEntry
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
    subgroup_markup,
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


@dataclass
class _DayData:
    by_group: dict[int, list[TimetableEntry]] = field(default_factory=dict)
    audiences: dict[int, str] = field(default_factory=dict)
    labels: dict[int, str] = field(default_factory=dict)
    parts: dict[int, str] = field(default_factory=dict)
    split: set[int] = field(default_factory=set)


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

    async def _day_data(self, for_date: date) -> _DayData:
        entries = await self.timetables_dao.get_entries(for_date)
        base_audiences = await self.timetables_dao.get_base_audiences(for_date)
        aliases = {
            g.group_id: g.alias for g in await self.study_groups_dao.get_all()
        }

        data = _DayData(audiences=base_audiences)
        for entry in entries:
            data.by_group.setdefault(entry.group_id, []).append(entry)

        for group_id, group_entries in sorted(data.by_group.items()):
            alias = aliases.get(group_id)
            label = f"{group_id} — {alias}" if alias else str(group_id)
            data.labels[group_id] = label
            data.parts[group_id] = format_group_schedule(
                label, base_audiences.get(group_id), group_entries, self.config
            )
            if any(e.subgroup is not None for e in group_entries):
                data.split.add(group_id)

        return data

    async def _send_rich(
        self, chat_id: int, markdown: str, reply_markup: InlineKeyboardMarkup | None = None
    ) -> None:
        await self.bot.send_rich_message(
            chat_id=chat_id,
            rich_message=InputRichMessage(markdown=markdown),
            reply_markup=reply_markup,
        )

    def _group_messages(
        self, for_date: date, data: _DayData, groups: Iterable[str]
    ) -> list[tuple[str, InlineKeyboardMarkup | None]]:
        messages = []
        for g in groups:
            if not g.isdigit() or int(g) not in data.parts:
                continue
            group_id = int(g)
            markup = (
                subgroup_markup(group_id, for_date) if group_id in data.split else None
            )
            messages.append((
                build_broadcast_message(for_date, [data.parts[group_id]], self.config),
                markup,
            ))
        return messages

    async def build_preview(
        self, for_date: date, group_id: int | None = None
    ) -> BroadcastPreview | None:
        data = await self._day_data(for_date)
        parts = data.parts
        lessons = sum(len(entries) for entries in data.by_group.values())
        if group_id is not None:
            parts = {group_id: parts[group_id]} if group_id in parts else {}
            lessons = len(data.by_group.get(group_id, []))
        if not parts:
            return None
        return BroadcastPreview(
            markdown=build_broadcast_message(for_date, list(parts.values()), self.config),
            groups=len(parts),
            lessons=lessons,
        )

    async def build_user_group_messages(
        self, for_date: date, groups: Iterable[str]
    ) -> list[tuple[str, InlineKeyboardMarkup | None]]:
        data = await self._day_data(for_date)
        return self._group_messages(for_date, data, groups)

    async def build_group_content(
        self, for_date: date, group_id: int, mode: str
    ) -> tuple[str, InlineKeyboardMarkup | None] | None:
        data = await self._day_data(for_date)
        entries = data.by_group.get(group_id)
        if not entries:
            return None
        markdown = build_broadcast_message(
            for_date,
            [
                format_group_schedule(
                    data.labels[group_id],
                    data.audiences.get(group_id),
                    entries,
                    self.config,
                    mode,
                )
            ],
            self.config,
        )
        markup = (
            subgroup_markup(group_id, for_date, mode)
            if group_id in data.split
            else None
        )
        return markdown, markup

    async def broadcast(self, for_date: date) -> BroadcastReport:
        data = await self._day_data(for_date)
        report = BroadcastReport(0, 0, 0, 0, len(data.parts))

        for user in await self.users_dao.get_all():
            if user.is_banned or not user.notifications_enabled:
                continue
            for markdown, markup in self._group_messages(for_date, data, user.groups):
                try:
                    await self._send_rich(user.user_id, markdown, markup)
                    report.users_sent += 1
                except TelegramForbiddenError:
                    report.users_failed += 1

        for chat in await self.group_chats_dao.get_all():
            for markdown, markup in self._group_messages(for_date, data, chat.groups):
                try:
                    await self._send_rich(chat.chat_id, markdown, markup)
                    report.chats_sent += 1
                except TelegramForbiddenError:
                    report.chats_failed += 1

        self._logger.info(
            "Broadcast %s: %s users, %s chats, %s groups",
            for_date, report.users_sent, report.chats_sent, report.groups,
        )
        return report
