import logging
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from timetabler.application.ports import ScheduleSender
from timetabler.domain.schemas import DaySchedule, TimetableEntry
from timetabler.infrastructure.database.dao import (
    ChannelsDAO,
    GroupChatsDAO,
    StudyGroupsDAO,
    TimetablesDAO,
    UsersDAO,
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
        sender: ScheduleSender,
        users_dao: UsersDAO,
        group_chats_dao: GroupChatsDAO,
        channels_dao: ChannelsDAO,
        study_groups_dao: StudyGroupsDAO,
        timetables_dao: TimetablesDAO,
    ) -> None:
        self.sender = sender
        self.users_dao = users_dao
        self.group_chats_dao = group_chats_dao
        self.channels_dao = channels_dao
        self.study_groups_dao = study_groups_dao
        self.timetables_dao = timetables_dao
        self._logger = logging.getLogger(__name__)

    async def day_schedule(self, for_date: date) -> DaySchedule:
        entries = await self.timetables_dao.get_entries(for_date)
        base_audiences = await self.timetables_dao.get_base_audiences(for_date)
        aliases = {
            g.group_id: g.alias for g in await self.study_groups_dao.get_all()
        }

        by_group: dict[int, list[TimetableEntry]] = {}
        for entry in entries:
            by_group.setdefault(entry.group_id, []).append(entry)

        labels = {}
        split: set[int] = set()
        for group_id, group_entries in by_group.items():
            alias = aliases.get(group_id)
            labels[group_id] = f"{group_id} — {alias}" if alias else str(group_id)
            if any(e.subgroup is not None for e in group_entries):
                split.add(group_id)

        return DaySchedule(
            by_group=by_group,
            audiences=base_audiences,
            labels=labels,
            split=split,
        )

    def _group_ids(self, day: DaySchedule, groups: Iterable[str]) -> list[int]:
        return [int(g) for g in groups if g.isdigit() and int(g) in day.by_group]

    async def broadcast(self, for_date: date) -> BroadcastReport:
        data = await self.day_schedule(for_date)
        report = BroadcastReport(0, 0, 0, 0, len(data.by_group))

        for user in await self.users_dao.get_all():
            if user.is_banned or not user.notifications_enabled:
                continue
            for group_id in self._group_ids(data, user.groups):
                if await self.sender.send_group_schedule(
                    user.user_id, for_date, data, group_id
                ):
                    report.users_sent += 1
                else:
                    report.users_failed += 1

        for channel in await self.channels_dao.get_enabled():
            if await self.sender.send_channel_schedule(channel.chat_id, for_date, data):
                report.chats_sent += 1
            else:
                report.chats_failed += 1

        for chat in await self.group_chats_dao.get_all():
            for group_id in self._group_ids(data, chat.groups):
                if await self.sender.send_group_schedule(
                    chat.chat_id, for_date, data, group_id
                ):
                    report.chats_sent += 1
                else:
                    report.chats_failed += 1

        self._logger.info(
            "Broadcast %s: %s users, %s chats, %s groups",
            for_date, report.users_sent, report.chats_sent, report.groups,
        )
        return report
