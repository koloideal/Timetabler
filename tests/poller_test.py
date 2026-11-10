import asyncio
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from timetabler.application.exceptions import TimetableParseError
from timetabler.application.ports import CreatorNotifier
from timetabler.application.services.broadcast import BroadcastService
from timetabler.application.services.detection import DetectionService
from timetabler.application.services.poller import SheetsPoller
from timetabler.application.services.revision import RevisionService
from timetabler.application.services.settings import SettingsService
from timetabler.domain.schemas import Revision, SheetsSettings
from timetabler.infrastructure.config.app import AppConfig


def _today() -> date:
    return datetime.now(ZoneInfo(AppConfig().revisions.update_timezone)).date()


def _settling(for_date: date) -> Revision:
    return Revision(
        id=1, for_date=for_date, weekday=for_date.weekday(), header=None,
        content_hash="h", group_hashes={}, base_audiences={}, kind="edit",
        changed_groups=[1], diff={}, parent_revision_id=None,
        status="settling", stable_polls=0, detected_at=datetime.now(timezone.utc),
        settled_at=None, published_at=None,
    )


class _Settings:
    async def get_sheets_settings(self):
        return SheetsSettings("A1:I200", "A1", 180, 3600, False)


class _Detection:
    def __init__(self, error=None):
        self.polled: list[date] = []
        self.error = error

    async def poll_day(self, for_date):
        self.polled.append(for_date)
        if self.error:
            raise self.error
        return None


class _Notifier:
    def __init__(self):
        self.errors = []

    async def notify_error(self, title, details=""):
        self.errors.append((title, details))


class _Broadcast:
    async def publish_revision(self, revision):
        pass


class _Revisions:
    def __init__(self, settling):
        self.settling = settling

    async def get_by_status(self, status):
        return list(self.settling) if status == "settling" else []


class _Session:
    async def commit(self):
        pass


class _Scope:
    def __init__(self, services):
        self.services = services

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, cls):
        return self.services[cls]


class _Container:
    def __init__(self, settling, error=None):
        self.detection = _Detection(error)
        self.notifier = _Notifier()
        self.services = {
            CreatorNotifier: self.notifier,
            SettingsService: _Settings(),
            DetectionService: self.detection,
            BroadcastService: _Broadcast(),
            RevisionService: _Revisions(settling),
            AsyncSession: _Session(),
            AppConfig: AppConfig(),
        }

    async def get(self, cls):
        return self.services[cls]

    def __call__(self):
        return _Scope(self.services)


def test_poll_interval_is_normal_without_settling():
    container = _Container([])
    delay = asyncio.run(SheetsPoller(container).poll_once())
    assert delay == 180


def test_poll_speeds_up_while_revision_is_settling():
    container = _Container([_settling(_today())])
    delay = asyncio.run(SheetsPoller(container).poll_once())
    assert delay == AppConfig().revisions.settle_poll_seconds


def test_settling_day_outside_window_is_still_polled():
    far = _today() + timedelta(days=5)
    container = _Container([_settling(far)])
    delay = asyncio.run(SheetsPoller(container).poll_once())
    assert far in container.detection.polled
    assert delay == AppConfig().revisions.settle_poll_seconds


def test_parse_error_is_sent_to_creator_once_until_it_changes():
    async def run():
        container = _Container([], error=TimetableParseError("Строка 5: непонятное время"))
        poller = SheetsPoller(container)
        await poller.poll_once()
        await poller.poll_once()
        return container.notifier.errors

    errors = asyncio.run(run())
    titles = [t for t, _ in errors]
    assert len(set(titles)) == len(titles) and titles
    assert all("Ошибка разбора таблицы" in t for t in titles)
    assert errors[0][1] == "Строка 5: непонятное время"
