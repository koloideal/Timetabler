import asyncio
import logging
from datetime import date, datetime, timezone
from time import monotonic
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from timetabler.application.ports import CreatorNotifier, ScheduleSender
from timetabler.application.services.lesson_timing import LessonTimingResolver
from timetabler.domain.schemas import (
    DaySchedule,
    GroupChat,
    ParsedTimetable,
    PublishReport,
    Revision,
    ResolvedLesson,
    TimetableEntry,
    User,
)
from timetabler.infrastructure.config.app import RevisionsConfig
from timetabler.infrastructure.database.dao import (
    ChannelsDAO,
    DeliveriesDAO,
    GroupChatsDAO,
    RevisionsDAO,
    SentMessagesDAO,
    StudyGroupsDAO,
    UsersDAO,
)


class BroadcastService:
    def __init__(
        self,
        sender: ScheduleSender,
        session: AsyncSession,
        session_maker: async_sessionmaker[AsyncSession],
        users_dao: UsersDAO,
        group_chats_dao: GroupChatsDAO,
        channels_dao: ChannelsDAO,
        study_groups_dao: StudyGroupsDAO,
        revisions_dao: RevisionsDAO,
        sent_messages_dao: SentMessagesDAO,
        deliveries_dao: DeliveriesDAO,
        notifier: CreatorNotifier,
        config: RevisionsConfig,
        timing: LessonTimingResolver,
    ) -> None:
        self.sender = sender
        self.session = session
        self.session_maker = session_maker
        self.users_dao = users_dao
        self.group_chats_dao = group_chats_dao
        self.channels_dao = channels_dao
        self.study_groups_dao = study_groups_dao
        self.revisions_dao = revisions_dao
        self.sent_messages_dao = sent_messages_dao
        self.deliveries_dao = deliveries_dao
        self.notifier = notifier
        self.config = config
        self.timing = timing
        self._logger = logging.getLogger(__name__)
        self._events = logging.getLogger("events")

    async def _build_day(
        self,
        entries: list[ResolvedLesson],
        base_audiences: dict[int, str],
        updated_label: str | None = None,
    ) -> DaySchedule:
        aliases = {
            g.group_id: g.alias for g in await self.study_groups_dao.get_all()
        }

        by_group: dict[int, list[ResolvedLesson]] = {}
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
            updated_label=updated_label,
        )

    async def day_schedule(self, for_date: date) -> DaySchedule:
        revision = await self.revisions_dao.get_published(for_date)
        if revision is None:
            return await self._build_day([], {})
        return await self.revision_schedule(revision)

    async def revision_schedule(self, revision: Revision) -> DaySchedule:
        entries = await self.revisions_dao.get_entries(revision.id)
        if entries and all(l.ordinal == 0 for l in entries):
            parsed = ParsedTimetable(
                entries=[
                    TimetableEntry(
                        group_id=l.group_id,
                        date=revision.for_date,
                        position=l.position,
                        subject=l.subject,
                        teacher=l.teacher,
                        audience=l.audience,
                        starts_at=l.source_time,
                        subgroup=l.subgroup,
                    )
                    for l in entries
                ]
            )
            entries = self.timing.resolve(parsed, revision.for_date)
        return await self._build_day(
            entries,
            revision.base_audiences,
            updated_label=self._update_label(revision.published_at),
        )

    async def publish_revision(self, revision: Revision) -> None:
        async with self.session_maker() as session:
            await self._with_session(session)._publish(revision)

    def _with_session(self, session: AsyncSession) -> "BroadcastService":
        return BroadcastService(
            self.sender, session, self.session_maker,
            UsersDAO(session), GroupChatsDAO(session), ChannelsDAO(session),
            StudyGroupsDAO(session), RevisionsDAO(session),
            SentMessagesDAO(session), DeliveriesDAO(session),
            self.notifier, self.config, self.timing,
        )

    @staticmethod
    def _changed_groups(revision: Revision, day: DaySchedule) -> set[int]:
        changed = set(revision.changed_groups)
        if not changed and revision.kind == "new":
            return set(day.by_group)
        return changed

    async def _publish(self, revision: Revision) -> None:
        started = monotonic()
        day = await self.revision_schedule(revision)
        label = self._update_label()
        changed = self._changed_groups(revision, day)

        recipients: list[tuple[str, int]] = []
        recipients += [
            ("channel", c.chat_id) for c in await self.channels_dao.get_enabled()
        ]

        chats = {
            c.chat_id: c
            for c in await self.group_chats_dao.get_active()
            if {g for g in c.study_groups if g in changed}
        }
        recipients += [("chat", chat_id) for chat_id in chats]

        changed_str = {str(g) for g in changed}
        recipients += [
            ("dm", u.user_id)
            for u in await self.users_dao.get_all()
            if not u.is_banned
            and u.notifications_enabled
            and changed_str & set(u.groups)
        ]

        await self.deliveries_dao.ensure(revision.id, recipients)
        await self.session.commit()

        planned = {k: sum(1 for kind, _ in recipients if kind == k) for k in ("channel", "chat", "dm")}
        self._events.info(
            "📬 Ревизия #%s на %s: рассылаю — каналов %s, групповых чатов %s, юзеров %s (группы %s)",
            revision.id, revision.for_date.strftime("%d.%m.%Y"),
            planned["channel"], planned["chat"], planned["dm"], sorted(changed),
        )

        stats = {k: [0, 0] for k in planned}
        pending = await self.deliveries_dao.get_pending(revision.id)
        pending.sort(key=lambda d: d.kind != "channel")
        for delivery in pending:
            try:
                if delivery.kind == "channel":
                    ok = await self._publish_channel(
                        delivery.chat_id, revision, day, label
                    )
                elif delivery.kind == "chat":
                    chat = chats.get(delivery.chat_id) or await self.group_chats_dao.get_by_id(
                        delivery.chat_id
                    )
                    ok = chat is not None and await self._publish_group_chat(
                        chat, revision, day, label
                    )
                else:
                    ok = await self._publish_dm(delivery.chat_id, revision, day, changed, label)
            except Exception:
                self._logger.exception(
                    "Delivery %s (%s to %s) crashed",
                    delivery.id, delivery.kind, delivery.chat_id,
                )
                ok = False
            stats[delivery.kind][0 if ok else 1] += 1
            await self.deliveries_dao.set_status(
                delivery.id, "sent" if ok else "failed"
            )
            await self.session.commit()
            await asyncio.sleep(self.config.send_delay_seconds)

        await self.revisions_dao.update_fields(
            revision.id,
            status="published",
            published_at=datetime.now(ZoneInfo(self.config.update_timezone)),
        )
        await self.session.commit()
        failed = sum(f for _, f in stats.values())
        total_age = int((datetime.now(timezone.utc) - revision.detected_at).total_seconds())
        self._events.info(
            "📤 Ревизия #%s на %s опубликована: каналов %s, чатов %s, юзеров %s%s — рассылка %.1f с, %s с после обнаружения",
            revision.id, revision.for_date.strftime("%d.%m.%Y"),
            stats["channel"][0], stats["chat"][0], stats["dm"][0],
            f", ошибок {failed} (каналов {stats['channel'][1]}, чатов {stats['chat'][1]}, юзеров {stats['dm'][1]})" if failed else "",
            monotonic() - started, total_age,
        )
        try:
            await self.notifier.notify_revision_report(
                PublishReport(
                    revision=revision,
                    seconds=monotonic() - started,
                    age_seconds=total_age,
                    channels=(stats["channel"][0], stats["channel"][1]),
                    chats=(stats["chat"][0], stats["chat"][1]),
                    users=(stats["dm"][0], stats["dm"][1]),
                    lessons_by_group={g: len(v) for g, v in day.by_group.items()},
                )
            )
        except Exception:
            self._logger.exception("Cannot send revision report to creator")

    def _update_label(self, at: datetime | None = None) -> str:
        tz = ZoneInfo(self.config.update_timezone)
        moment = at.astimezone(tz) if at is not None else datetime.now(tz)
        return f"Обновлено {moment.strftime('%d.%m в %H:%M')}"

    async def _publish_channel(
        self, chat_id: int, revision: Revision, day: DaySchedule, label: str
    ) -> bool:
        if await self.sent_messages_dao.get_for_revision(revision.id, chat_id):
            return True

        prev = [
            m for m in await self.sent_messages_dao.get_for_day(chat_id, revision.for_date)
            if m.revision_id != revision.id
        ]
        message_id = await self.sender.send_channel_schedule(
            chat_id, revision.for_date, day, label
        )
        if message_id is None:
            await self.channels_dao.set_status(chat_id, "disabled")
            await self.notifier.notify_creator(
                self.config.channel_send_failed_text.format(chat_id=chat_id)
            )
            return False
        await self.sent_messages_dao.add(
            revision.id, revision.for_date, chat_id, message_id,
            "channel", [str(g) for g in day.by_group],
        )
        for stale in prev:
            await self.sender.delete_message(chat_id, stale.message_id)
            await self.sent_messages_dao.remove(stale.id)
        return True

    async def _publish_group_chat(
        self, chat: GroupChat, revision: Revision, day: DaySchedule, label: str
    ) -> bool:
        changed = self._changed_groups(revision, day)
        relevant = [g for g in chat.study_groups if g in changed]
        if not relevant:
            return True
        to_send = [
            g for g in relevant
            if g in day.by_group
            and g
            not in {
                int(sg)
                for m in await self.sent_messages_dao.get_for_revision(
                    revision.id, chat.chat_id
                )
                for sg in m.groups
            }
        ]
        result = await self._deliver_group_chat(
            chat, revision.for_date, day, revision, label, to_send,
            cleanup_groups=relevant,
        )
        return result != "failed"

    async def _publish_dm(
        self,
        user_id: int,
        revision: Revision,
        day: DaySchedule,
        changed: set[int],
        label: str,
    ) -> bool:
        user = await self.users_dao.get_by_id(user_id)
        if user is None:
            return False

        relevant = [g for g in sorted(changed) if str(g) in user.groups]
        needed = [g for g in relevant if g in day.by_group]
        already = {
            int(g)
            for m in await self.sent_messages_dao.get_for_revision(revision.id, user_id)
            for g in m.groups
        }
        prev = [
            m for m in await self.sent_messages_dao.get_for_day(user_id, revision.for_date)
            if m.revision_id != revision.id
        ]
        note = label

        ok = True
        sent_now = []
        dropped: set[int] = set()

        async def drop_old(group_id: int) -> None:
            for old in prev:
                if old.id in dropped or str(group_id) not in old.groups:
                    continue
                dropped.add(old.id)
                await self.sender.delete_message(user_id, old.message_id)
                await self.sent_messages_dao.remove(old.id)

        for group_id in needed:
            if group_id in already:
                continue
            message_id = await self.sender.send_group_schedule(
                user_id, revision.for_date, day, group_id, note,
                mode=user.subgroup_mode,
            )
            if message_id is None:
                ok = False
                continue
            sent_now.append(message_id)
            await self.sent_messages_dao.add(
                revision.id, revision.for_date, user_id, message_id,
                "dm", [str(group_id)],
            )
            await drop_old(group_id)

        for group_id in relevant:
            if group_id not in day.by_group:
                await drop_old(group_id)

        if user.pin_enabled:
            await self._apply_user_pins(user, sent_now)
        return ok

    async def drop_user_group_messages(self, user_id: int, group_id: int) -> None:
        user = await self.users_dao.get_by_id(user_id)
        for m in await self.sent_messages_dao.get_for_user_group(
            user_id, str(group_id)
        ):
            await self.sender.delete_message(user_id, m.message_id)
            await self.sent_messages_dao.remove(m.id)
            if user is not None and m.message_id in user.pinned_message_ids:
                await self.sender.unpin_chat_message(user_id, m.message_id)
                await self.users_dao.set_pinned_messages(
                    user_id,
                    [mid for mid in user.pinned_message_ids if mid != m.message_id],
                )

    async def deliver_to_chat(
        self, chat: GroupChat, for_date: date, day: DaySchedule | None = None
    ) -> str:
        day = day or await self.day_schedule(for_date)
        groups = [g for g in chat.study_groups if g in day.by_group]
        if not groups:
            return "empty"
        revision = await self.revisions_dao.get_published(for_date)
        return await self._deliver_group_chat(
            chat, for_date, day, revision, day.updated_label, groups
        )

    async def _deliver_group_chat(
        self,
        chat: GroupChat,
        for_date: date,
        day: DaySchedule,
        revision: Revision | None,
        note: str | None,
        group_ids: list[int],
        cleanup_groups: list[int] | None = None,
    ) -> str:
        message_ids = []
        for group_id in group_ids:
            delivery = await self.sender.send_chat_schedule(
                chat.chat_id, for_date, day, group_id, note
            )
            if delivery.migrate_to is not None:
                moved = await self.group_chats_dao.update_chat_id(
                    chat.chat_id, delivery.migrate_to
                )
                if moved is None:
                    await self._disable_chat(chat)
                    return "failed"
                chat = moved
                delivery = await self.sender.send_chat_schedule(
                    chat.chat_id, for_date, day, group_id, note
                )
            if delivery.forbidden or delivery.migrate_to is not None:
                await self._disable_chat(chat)
                return "failed"
            if delivery.failed:
                return "failed"
            if delivery.message_id is None:
                continue
            message_ids.append(delivery.message_id)
            await self.sent_messages_dao.add(
                revision.id if revision else None,
                for_date, chat.chat_id, delivery.message_id,
                "chat", [str(group_id)],
            )
            if revision is not None:
                await self._drop_old_chat_messages(
                    chat.chat_id, for_date, revision, {str(group_id)}, message_ids
                )

        if revision is not None:
            await self._drop_old_chat_messages(
                chat.chat_id, for_date, revision,
                {
                    str(g)
                    for g in (cleanup_groups if cleanup_groups is not None else group_ids)
                },
                message_ids,
            )

        if not message_ids:
            return "empty"

        await self._apply_pins(chat, message_ids)
        return "sent"

    async def _drop_old_chat_messages(
        self,
        chat_id: int,
        for_date: date,
        revision: Revision,
        groups: set[str],
        keep_ids: list[int],
    ) -> None:
        for old in await self.sent_messages_dao.get_for_day(chat_id, for_date):
            if old.revision_id == revision.id or old.message_id in keep_ids:
                continue
            if not groups & set(old.groups):
                continue
            await self.sender.delete_message(chat_id, old.message_id)
            await self.sent_messages_dao.remove(old.id)

    async def _apply_pins(self, chat: GroupChat, message_ids: list[int]) -> None:
        if not chat.pin_enabled:
            return
        pinned: list[int] = []
        for message_id in message_ids:
            if not await self.sender.pin_chat_message(chat.chat_id, message_id):
                for mid in pinned:
                    await self.sender.unpin_chat_message(chat.chat_id, mid)
                await self._disable_pin(chat)
                return
            pinned.append(message_id)
        for old_id in chat.pinned_message_ids:
            if old_id not in pinned:
                await self.sender.unpin_chat_message(chat.chat_id, old_id)
        await self.group_chats_dao.set_pinned_messages(chat.chat_id, pinned)

    async def _apply_user_pins(self, user: User, message_ids: list[int]) -> None:
        pinned: list[int] = []
        for message_id in message_ids:
            if await self.sender.pin_chat_message(user.user_id, message_id):
                pinned.append(message_id)
        for old_id in user.pinned_message_ids:
            if old_id not in pinned:
                await self.sender.unpin_chat_message(user.user_id, old_id)
        await self.users_dao.set_pinned_messages(user.user_id, pinned)

    async def _disable_pin(self, chat: GroupChat) -> None:
        await self.group_chats_dao.set_pin_enabled(chat.chat_id, False)
        notify_id = chat.configured_by_user_id or chat.added_by_user_id
        if notify_id:
            await self.sender.send_text(
                notify_id,
                self.config.chat_pin_failed_text.format(
                    title=chat.title or chat.chat_id
                ),
            )

    async def _disable_chat(self, chat: GroupChat) -> None:
        await self.group_chats_dao.set_status(chat.chat_id, "disabled")
        notify_id = chat.configured_by_user_id or chat.added_by_user_id
        if notify_id:
            await self.sender.send_text(
                notify_id,
                self.config.chat_send_failed_text.format(
                    title=chat.title or chat.chat_id
                ),
            )
