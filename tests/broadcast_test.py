from datetime import date, datetime, timezone

import asyncio


from timetabler.application.ports import ChatDelivery
from timetabler.application.services.broadcast import BroadcastService
from timetabler.domain.schemas import (
    Delivery,
    GroupChat,
    ResolvedLesson,
    Revision,
    SentMessage,
    User,
)
from timetabler.infrastructure.config.app import RevisionsConfig

FOR_DATE = date(2026, 11, 5)


def _lesson(group_id=2124, subject="Математика") -> ResolvedLesson:
    return ResolvedLesson(
        group_id=group_id,
        date=FOR_DATE,
        position=1,
        subgroup=None,
        ordinal=1,
        slot=1,
        half="full",
        start=32400,
        end=38100,
        kind="lesson",
        subject=subject,
        teacher=None,
        audience=None,
        flags=frozenset(),
        source_time=None,
    )


def _revision(**kw) -> Revision:
    base = dict(
        id=1,
        for_date=FOR_DATE,
        weekday=FOR_DATE.weekday(),
        header=None,
        content_hash="h",
        group_hashes={2124: "x"},
        base_audiences={},
        kind="edit",
        changed_groups=[2124],
        diff={},
        parent_revision_id=None,
        status="approved",
        stable_polls=0,
        detected_at=datetime.now(timezone.utc),
        settled_at=None,
        published_at=None,
    )
    base.update(kw)
    return Revision(**base)


def _user(groups=("2124",), **kw) -> User:
    base = dict(
        user_id=42,
        username="u",
        is_banned=False,
        notifications_enabled=True,
        groups=list(groups),
        created_at=datetime.now(timezone.utc),
        subgroup_mode="a",
        pin_enabled=False,
        pinned_message_ids=[],
        main_group=None,
    )
    base.update(kw)
    return User(**base)


class FakeSender:
    def __init__(self):
        self.group_schedules = []
        self.deleted = []
        self.texts = []
        self._next_id = 100

    async def send_group_schedule(self, chat_id, for_date, day, group_id,
                                  note=None, mode="a"):
        self._next_id += 1
        self.group_schedules.append((chat_id, group_id))
        return self._next_id

    async def send_channel_schedule(self, chat_id, for_date, day, note=None):
        return None

    async def edit_channel_schedule(self, chat_id, message_id, for_date, day,
                                    note=None):
        return False

    async def send_chat_schedule(self, chat_id, for_date, day, group_id,
                                 note=None):
        return ChatDelivery()

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))

    async def pin_chat_message(self, chat_id, message_id):
        return True

    async def unpin_chat_message(self, chat_id, message_id):
        pass

    async def send_text(self, chat_id, text):
        self.texts.append((chat_id, text))
        return True


class FakeSession:
    async def commit(self):
        pass


class FakeUsersDAO:
    def __init__(self, users):
        self.users = {u.user_id: u for u in users}
        self.pinned: dict[int, list[int]] = {}

    async def get_all(self):
        return list(self.users.values())

    async def get_by_id(self, user_id):
        return self.users.get(user_id)

    async def set_pinned_messages(self, user_id, message_ids):
        self.pinned[user_id] = list(message_ids)


class FakeGroupChatsDAO:
    def __init__(self, chats=()):
        self.chats = {c.chat_id: c for c in chats}
        self.disabled: list[int] = []
        self.pin_disabled: list[int] = []

    async def get_active(self):
        return [c for c in self.chats.values() if c.status == "active"]

    async def set_status(self, chat_id, status):
        if status == "disabled":
            self.disabled.append(chat_id)
        self.chats[chat_id].status = status

    async def set_pin_enabled(self, chat_id, enabled):
        if not enabled:
            self.pin_disabled.append(chat_id)
        self.chats[chat_id].pin_enabled = enabled

    async def set_pinned_messages(self, chat_id, message_ids):
        self.chats[chat_id].pinned_message_ids = list(message_ids)

    async def update_chat_id(self, old, new):
        return None


class FakeChannelsDAO:
    async def get_enabled(self):
        return []

    async def set_status(self, chat_id, status):
        pass


class FakeStudyGroupsDAO:
    async def get_all(self):
        return []


class FakeRevisionsDAO:
    def __init__(self, entries):
        self.entries = entries
        self.updated = []

    async def get_entries(self, revision_id):
        return list(self.entries)

    async def get_published(self, for_date):
        return None

    async def update_fields(self, revision_id, **values):
        self.updated.append(values)


class FakeSentMessagesDAO:
    def __init__(self):
        self.rows: list[SentMessage] = []
        self._next_id = 1

    async def get_for_day(self, chat_id, for_date):
        return [m for m in self.rows
                if m.chat_id == chat_id and m.for_date == for_date]

    async def get_for_revision(self, revision_id, chat_id):
        return [m for m in self.rows
                if m.revision_id == revision_id and m.chat_id == chat_id]

    async def get_for_user_group(self, chat_id, group):
        return [m for m in self.rows
                if m.chat_id == chat_id and group in m.groups]

    async def add(self, revision_id, for_date, chat_id, message_id, kind,
                  groups):
        row = SentMessage(
            id=self._next_id,
            revision_id=revision_id,
            for_date=for_date,
            chat_id=chat_id,
            message_id=message_id,
            kind=kind,
            groups=list(groups),
            sent_at=None,
        )
        self._next_id += 1
        self.rows.append(row)
        return row

    async def set_revision(self, row_id, revision_id):
        pass

    async def remove(self, row_id):
        self.rows = [m for m in self.rows if m.id != row_id]


class FakeDeliveriesDAO:
    def __init__(self):
        self.rows: list[Delivery] = []
        self._next_id = 1

    async def ensure(self, revision_id, recipients):
        for kind, chat_id in recipients:
            if any(d.revision_id == revision_id and d.kind == kind
                   and d.chat_id == chat_id for d in self.rows):
                continue
            self.rows.append(Delivery(
                id=self._next_id,
                revision_id=revision_id,
                kind=kind,
                chat_id=chat_id,
                status="pending",
                sent_at=None,
            ))
            self._next_id += 1

    async def get_pending(self, revision_id):
        return [d for d in self.rows
                if d.revision_id == revision_id and d.status == "pending"]

    async def set_status(self, delivery_id, status):
        for d in self.rows:
            if d.id == delivery_id:
                d.status = status


class FakeNotifier:
    def __init__(self):
        self.messages = []

    async def notify_creator(self, text):
        self.messages.append(text)


def make_service(*, users=(_user(),), entries=(_lesson(),),
                 sender=None, sent=None, chats=()):
    service = BroadcastService(
        sender or FakeSender(),
        FakeSession(),
        None,
        FakeUsersDAO(users),
        FakeGroupChatsDAO(chats),
        FakeChannelsDAO(),
        FakeStudyGroupsDAO(),
        FakeRevisionsDAO(entries),
        sent or FakeSentMessagesDAO(),
        FakeDeliveriesDAO(),
        FakeNotifier(),
        RevisionsConfig(send_delay_seconds=0),
        None,
    )
    return service


def test_publish_delivers_to_subscribed_user():
    asyncio.run(_test_publish_delivers_to_subscribed_user())


async def _test_publish_delivers_to_subscribed_user():
    sender = FakeSender()
    service = make_service(sender=sender)
    await service._publish(_revision())
    assert sender.group_schedules == [(42, 2124)]


def test_publish_idempotent_no_duplicate_sends():
    asyncio.run(_test_publish_idempotent_no_duplicate_sends())


async def _test_publish_idempotent_no_duplicate_sends():
    sender = FakeSender()
    service = make_service(sender=sender)
    rev = _revision()
    await service._publish(rev)
    await service._publish(rev)
    assert sender.group_schedules == [(42, 2124)]


def test_publish_skips_already_sent_groups():
    asyncio.run(_test_publish_skips_already_sent_groups())


async def _test_publish_skips_already_sent_groups():
    sent = FakeSentMessagesDAO()
    await sent.add(1, FOR_DATE, 42, 555, "dm", ["2124"])
    sender = FakeSender()
    service = make_service(sender=sender, sent=sent)
    await service._publish(_revision())
    assert sender.group_schedules == []


def test_publish_skips_unsubscribed_and_banned():
    asyncio.run(_test_publish_skips_unsubscribed_and_banned())


async def _test_publish_skips_unsubscribed_and_banned():
    sender = FakeSender()
    service = make_service(
        users=(_user(groups=("9999",)), _user(is_banned=True, user_id=7)),
        sender=sender,
    )
    await service._publish(_revision())
    assert sender.group_schedules == []


def test_badrequest_failure_does_not_disable_chat():
    asyncio.run(_test_badrequest_failure_does_not_disable_chat())


async def _test_badrequest_failure_does_not_disable_chat():
    class BadRequestSender(FakeSender):
        async def send_chat_schedule(self, chat_id, for_date, day, group_id,
                                     note=None):
            return ChatDelivery(failed=True)

    chat = GroupChat(
        chat_id=-100,
        title="t",
        status="active",
        study_groups=[2124],
        pin_enabled=False,
        pinned_message_ids=[],
        added_by_user_id=1,
        configured_by_user_id=None,
        created_at=datetime.now(timezone.utc),
    )
    chats = FakeGroupChatsDAO([chat])
    service = BroadcastService(
        BadRequestSender(), FakeSession(), None,
        FakeUsersDAO([]), chats, FakeChannelsDAO(), FakeStudyGroupsDAO(),
        FakeRevisionsDAO([_lesson()]), FakeSentMessagesDAO(),
        FakeDeliveriesDAO(), FakeNotifier(),
        RevisionsConfig(send_delay_seconds=0), None,
    )
    result = await service._deliver_group_chat(
        chat, FOR_DATE, await service.day_schedule(FOR_DATE),
        _revision(), "note", [2124],
    )
    assert result == "failed"
    assert chats.disabled == []


def test_forbidden_disables_chat():
    asyncio.run(_test_forbidden_disables_chat())


async def _test_forbidden_disables_chat():
    class ForbiddenSender(FakeSender):
        async def send_chat_schedule(self, chat_id, for_date, day, group_id,
                                     note=None):
            return ChatDelivery(failed=True, forbidden=True)

    chat = GroupChat(
        chat_id=-100,
        title="t",
        status="active",
        study_groups=[2124],
        pin_enabled=False,
        pinned_message_ids=[],
        added_by_user_id=1,
        configured_by_user_id=None,
        created_at=datetime.now(timezone.utc),
    )
    chats = FakeGroupChatsDAO([chat])
    service = BroadcastService(
        ForbiddenSender(), FakeSession(), None,
        FakeUsersDAO([]), chats, FakeChannelsDAO(), FakeStudyGroupsDAO(),
        FakeRevisionsDAO([_lesson()]), FakeSentMessagesDAO(),
        FakeDeliveriesDAO(), FakeNotifier(),
        RevisionsConfig(send_delay_seconds=0), None,
    )
    result = await service._deliver_group_chat(
        chat, FOR_DATE, await service.day_schedule(FOR_DATE),
        _revision(), "note", [2124],
    )
    assert result == "failed"
    assert chats.disabled == [-100]


class _Channel:
    def __init__(self, chat_id):
        self.chat_id = chat_id


class _ChannelsDAO(FakeChannelsDAO):
    async def get_enabled(self):
        return [_Channel(-500)]


class _ChannelSender(FakeSender):
    def __init__(self):
        super().__init__()
        self.events = []

    async def send_channel_schedule(self, chat_id, for_date, day, note=None):
        self.events.append(("send", chat_id))
        return 900

    async def edit_channel_schedule(self, chat_id, message_id, for_date, day,
                                    note=None):
        self.events.append(("edit", message_id))
        return True

    async def delete_message(self, chat_id, message_id):
        self.events.append(("delete", message_id))


def test_channel_always_resends_and_deletes_old():
    asyncio.run(_test_channel_always_resends_and_deletes_old())


async def _test_channel_always_resends_and_deletes_old():
    sent = FakeSentMessagesDAO()
    await sent.add(0, FOR_DATE, -500, 777, "channel", ["2124"])
    sender = _ChannelSender()
    service = make_service(users=(), sender=sender, sent=sent)
    service.channels_dao = _ChannelsDAO()
    await service._publish(_revision())
    assert sender.events == [("send", -500), ("delete", 777)]
    assert [m.message_id for m in sent.rows] == [900]


class _OrderSender(FakeSender):
    def __init__(self):
        super().__init__()
        self.events = []

    async def send_group_schedule(self, chat_id, for_date, day, group_id,
                                  note=None, mode="a"):
        self.events.append(("send", group_id))
        return await super().send_group_schedule(
            chat_id, for_date, day, group_id, note, mode
        )

    async def delete_message(self, chat_id, message_id):
        self.events.append(("delete", message_id))


def test_dm_deletes_old_right_after_each_new_group():
    asyncio.run(_test_dm_deletes_old_right_after_each_new_group())


async def _test_dm_deletes_old_right_after_each_new_group():
    sent = FakeSentMessagesDAO()
    await sent.add(0, FOR_DATE, 42, 11, "dm", ["2124"])
    await sent.add(0, FOR_DATE, 42, 12, "dm", ["3124"])
    sender = _OrderSender()
    service = make_service(
        users=(_user(groups=("2124", "3124")),),
        entries=(_lesson(2124), _lesson(3124)),
        sender=sender, sent=sent,
    )
    await service._publish(_revision(changed_groups=[2124, 3124]))
    assert sender.events == [
        ("send", 2124), ("delete", 11), ("send", 3124), ("delete", 12),
    ]


def test_only_changed_group_is_sent_to_multi_group_user():
    asyncio.run(_test_only_changed_group_is_sent_to_multi_group_user())


async def _test_only_changed_group_is_sent_to_multi_group_user():
    sent = FakeSentMessagesDAO()
    await sent.add(0, FOR_DATE, 42, 11, "dm", ["2124"])
    sender = _OrderSender()
    service = make_service(
        users=(_user(groups=("2124", "3124")),),
        entries=(_lesson(2124), _lesson(3124)),
        sender=sender, sent=sent,
    )
    await service._publish(_revision(changed_groups=[3124]))
    assert sender.group_schedules == [(42, 3124)]
    assert ("delete", 11) not in sender.events
    assert any(m.message_id == 11 for m in sent.rows)
