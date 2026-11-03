import logging
from dataclasses import dataclass
from datetime import date

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

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

    async def broadcast(self, for_date: date) -> BroadcastReport:
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

        def group_part(group_id: int) -> str:
            return format_group_schedule(
                label(group_id), base_audiences.get(group_id), by_group[group_id], self.config
            )

        report = BroadcastReport(0, 0, 0, 0, len(by_group))

        for user in await self.users_dao.get_all():
            parts = [
                group_part(int(g))
                for g in user.groups
                if g.isdigit() and int(g) in by_group
            ]
            if not parts:
                continue
            try:
                await self.bot.send_message(
                    user.user_id, build_broadcast_message(for_date, parts, self.config)
                )
                report.users_sent += 1
            except TelegramForbiddenError:
                report.users_failed += 1

        for chat in await self.group_chats_dao.get_all():
            parts = [
                group_part(int(g))
                for g in chat.groups
                if g.isdigit() and int(g) in by_group
            ]
            if not parts:
                continue
            try:
                await self.bot.send_message(
                    chat.chat_id, build_broadcast_message(for_date, parts, self.config)
                )
                report.chats_sent += 1
            except TelegramForbiddenError:
                report.chats_failed += 1

        self._logger.info(
            "Broadcast %s: %s users, %s chats, %s groups",
            for_date, report.users_sent, report.chats_sent, report.groups,
        )
        return report
