import asyncio
from datetime import datetime, timezone

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.methods import CopyMessage

from timetabler.application.ports.mass_sender import COPY_BLOCKED, COPY_FAILED, COPY_OK
from timetabler.application.services.audience import (
    MODE_ALL,
    MODE_COURSES,
    MODE_GROUPS,
    MODE_SPECIALTIES,
    Audience,
    AudienceService,
    AudienceSpec,
)
from timetabler.application.services.mass_broadcast import MassBroadcastService
from timetabler.domain.groups import course_of, specialty_labels
from timetabler.domain.schemas import GroupChat, StudyGroup, User
from timetabler.infrastructure.config.app import MassBroadcastConfig
from timetabler.presentation.admin_dialogs import build_admin_panel_dialog
from timetabler.presentation.telegram.mass_sender import TelegramMassSender

NOW = datetime.now(timezone.utc)


def _sg(gid, alias=None) -> StudyGroup:
    return StudyGroup(group_id=gid, alias=alias, created_at=NOW)


GROUPS = [
    _sg(1124, "БУАиК после 9, 3 курс"),
    _sg(1126, "БУАиК после 9, 1 курс"),
    _sg(2124, "РиСПОИС, 3 курс"),
    _sg(2126, "РиСПОИС, 1 курс"),
    _sg(3125),
]


def _user(uid, groups, banned=False) -> User:
    return User(
        user_id=uid, username=None, is_banned=banned, notifications_enabled=True,
        groups=list(groups), created_at=NOW,
    )


def _chat(cid, groups) -> GroupChat:
    return GroupChat(
        chat_id=cid, title="t", status="active", study_groups=list(groups),
        pin_enabled=False, pinned_message_ids=[], added_by_user_id=None,
        configured_by_user_id=None, created_at=NOW,
    )


class _UsersDAO:
    async def get_all(self):
        return [
            _user(1, ["1124"]), _user(2, ["2126"]), _user(3, []),
            _user(4, ["1124"], banned=True), _user(5, ["1126", "2124"]),
        ]


class _ChatsDAO:
    async def get_active(self):
        return [_chat(-1, [1124]), _chat(-2, [2126]), _chat(-3, [])]


class _GroupsDAO:
    async def get_all(self):
        return list(GROUPS)


def _audience() -> AudienceService:
    return AudienceService(_UsersDAO(), _ChatsDAO(), _GroupsDAO())


def _resolve(**kw) -> Audience:
    return asyncio.run(_audience().resolve(AudienceSpec(**kw)))


def test_course_and_specialty_helpers():
    assert [course_of(g) for g in GROUPS] == [3, 1, 3, 1, 2]
    assert specialty_labels(GROUPS) == {
        "1": "БУАиК", "2": "РиСПОИС", "3": "Спец. 3",
    }


def test_all_skips_banned_but_keeps_groupless_users_and_all_chats():
    a = _resolve(mode=MODE_ALL)
    assert a.user_ids == [1, 2, 3, 5]
    assert a.chat_ids == [-1, -2, -3]


def test_without_chats_never_includes_chats():
    assert _resolve(mode=MODE_ALL, include_chats=False).chat_ids == []


def test_courses_filter_users_and_chats():
    a = _resolve(mode=MODE_COURSES, values=["1"])
    assert a.user_ids == [2, 5]
    assert a.chat_ids == [-2]


def test_specialties_filter():
    a = _resolve(mode=MODE_SPECIALTIES, values=["1"])
    assert a.user_ids == [1, 5]
    assert a.chat_ids == [-1]


def test_groups_filter():
    a = _resolve(mode=MODE_GROUPS, values=["2124"])
    assert a.user_ids == [5]
    assert a.chat_ids == []


def test_options_per_mode():
    svc = _audience()
    assert asyncio.run(svc.options(MODE_COURSES)) == [
        ("1 курс", "1"), ("2 курс", "2"), ("3 курс", "3"),
    ]
    assert asyncio.run(svc.options(MODE_SPECIALTIES))[0] == ("БУАиК", "1")


class _Sender:
    def __init__(self, results=None, delay=0.0):
        self.calls = []
        self.results = results or {}
        self.delay = delay

    async def copy_to(self, chat_id, from_chat_id, message_id):
        self.calls.append((chat_id, from_chat_id, message_id))
        await asyncio.sleep(self.delay)
        return self.results.get(chat_id, COPY_OK)


class _Notifier:
    def __init__(self):
        self.texts = []

    async def notify_creator(self, text):
        self.texts.append(text)


def _service(sender, notifier=None):
    return MassBroadcastService(
        sender, notifier or _Notifier(), MassBroadcastConfig(send_interval_seconds=0)
    )


def test_job_runs_in_background_and_reports():
    async def run():
        notifier = _Notifier()
        sender = _Sender({2: COPY_BLOCKED, -1: COPY_FAILED})
        svc = _service(sender, notifier)
        job = svc.start(Audience([1, 2], [-1]), 99, 7, "все")
        assert job.running and svc.active() is job
        await job.task
        return job, sender, notifier, svc

    job, sender, notifier, svc = asyncio.run(run())
    assert (job.sent, job.blocked, job.failed) == (1, 1, 1)
    assert sender.calls == [(1, 99, 7), (2, 99, 7), (-1, 99, 7)]
    assert not job.running and svc.active() is None
    assert len(notifier.texts) == 1 and "Доставлено: 1 из 3" in notifier.texts[0]


def test_second_job_is_rejected_while_running():
    async def run():
        svc = _service(_Sender(delay=0.01))
        job = svc.start(Audience([1, 2, 3], []), 1, 1, "x")
        try:
            svc.start(Audience([1], []), 1, 1, "y")
        except RuntimeError:
            rejected = True
        else:
            rejected = False
        await job.task
        return rejected

    assert asyncio.run(run()) is True


def test_cancel_stops_remaining_recipients():
    async def run():
        sender = _Sender(delay=0.02)
        svc = _service(sender)
        job = svc.start(Audience(list(range(50)), []), 1, 1, "x")
        await asyncio.sleep(0.05)
        assert svc.cancel(job.id)
        await job.task
        return job

    job = asyncio.run(run())
    assert job.cancelled and 0 < job.done < 50


class _FakeBot:
    def __init__(self, *errors):
        self.errors = list(errors)
        self.calls = 0

    async def copy_message(self, chat_id, from_chat_id, message_id):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)


def _method():
    return CopyMessage(chat_id=1, from_chat_id=2, message_id=3)


def _sender(*errors):
    bot = _FakeBot(*errors)
    cfg = MassBroadcastConfig(max_retry_wait_seconds=0)
    return TelegramMassSender(bot, cfg), bot


def test_flood_wait_is_retried_not_failed():
    sender, bot = _sender(
        TelegramRetryAfter(_method(), "flood", 0),
        TelegramRetryAfter(_method(), "flood", 0),
    )
    assert asyncio.run(sender.copy_to(1, 2, 3)) == COPY_OK
    assert bot.calls == 3


def test_forbidden_is_blocked_and_bad_request_failed():
    s1, _ = _sender(TelegramForbiddenError(_method(), "blocked"))
    assert asyncio.run(s1.copy_to(1, 2, 3)) == COPY_BLOCKED
    s2, _ = _sender(TelegramBadRequest(_method(), "chat not found"))
    assert asyncio.run(s2.copy_to(1, 2, 3)) == COPY_FAILED


def test_admin_dialog_with_broadcast_windows_builds():
    build_admin_panel_dialog()
