from datetime import date, datetime, timezone

import asyncio


from timetabler.application.services.detection import (
    DetectionService,
    _grid_hash,
    _normalize_cell,
)
from timetabler.domain.schemas import (
    ParsedTimetable,
    ResolvedLesson,
    Revision,
    SheetSource,
    SheetsSettings,
    TimetableEntry,
)
from timetabler.infrastructure.config.app import AppConfig

FOR_DATE = date(2026, 11, 5)  # Thursday
MARKER = f"РАСПИСАНИЕ ЗАНЯТИЙ НА {FOR_DATE:%d.%m.%Y}"


def _lesson(subject: str, position: int = 1) -> ResolvedLesson:
    return ResolvedLesson(
        group_id=2124,
        date=FOR_DATE,
        position=position,
        subgroup=None,
        ordinal=1,
        slot=position,
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


def _entry(subject: str, position: int = 1) -> TimetableEntry:
    return TimetableEntry(
        group_id=2124,
        date=FOR_DATE,
        position=position,
        subject=subject,
    )


def _revision(rev_id: int, status: str, **kw) -> Revision:
    base = dict(
        id=rev_id,
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
        status=status,
        stable_polls=0,
        detected_at=datetime.now(timezone.utc),
        settled_at=None,
        published_at=None,
    )
    base.update(kw)
    return Revision(**base)


class FakeSheetsClient:
    def __init__(self, values):
        self.values = values

    async def read_values(self, spreadsheet_id, a1_range):
        return self.values


class FakeParser:
    def __init__(self, parsed):
        self.parsed = parsed

    def parse(self, values, default_date):
        return self.parsed


class FakeTiming:
    def resolve(self, parsed, for_date):
        return list(parsed.resolved)


class FakeSettingsService:
    def __init__(self, require_confirmation=False):
        self.settings = SheetsSettings(
            schedule_range="A1:I200",
            date_cell="A1",
            poll_interval_seconds=180,
            lookahead_poll_seconds=3600,
            require_confirmation=require_confirmation,
        )

    async def get_sheets_settings(self):
        return self.settings


class FakeSheetsService:
    def __init__(self, last_hash=None):
        self.source = SheetSource(
            weekday=FOR_DATE.weekday(),
            spreadsheet_id="sid",
            last_header=None,
            last_hash=last_hash,
        )

    async def get_source(self, weekday):
        return self.source if weekday == self.source.weekday else None

    async def set_last_hash(self, weekday, content_hash):
        self.source.last_hash = content_hash

    async def mark_header(self, weekday, marker):
        self.source.last_header = marker


class FakeNotifier:
    def __init__(self):
        self.approvals = []

    async def ask_revision_approval(self, revision):
        self.approvals.append(revision)


class FakeRevisionService:
    def __init__(self):
        self.revisions: dict[int, Revision] = {}
        self.entries: dict[int, list] = {}
        self._next_id = 1

    def _save(self, rev):
        self.revisions[rev.id] = rev
        return rev

    def seed(self, rev, entries=None):
        self._save(rev)
        self.entries[rev.id] = entries or []
        self._next_id = max(self._next_id, rev.id + 1)
        return rev

    async def get_settling(self, for_date):
        for r in self.revisions.values():
            if r.for_date == for_date and r.status == "settling":
                return r
        return None

    async def get_published(self, for_date):
        for r in sorted(self.revisions.values(), key=lambda r: -r.id):
            if r.for_date == for_date and r.status == "published":
                return r
        return None

    async def get_entries(self, revision_id):
        return list(self.entries.get(revision_id, []))

    async def create(self, *, parsed, **kw):
        rev = _revision(self._next_id, status="settling", **kw)
        self._next_id += 1
        self.entries[rev.id] = list(parsed.resolved or parsed.entries)
        return self._save(rev)

    async def refresh_candidate(self, settling, *, parsed, **kw):
        old = self.revisions[settling.id]
        rev = _revision(old.id, old.status, stable_polls=0,
                        detected_at=old.detected_at, **kw)
        self.entries[rev.id] = list(parsed.resolved or parsed.entries)
        return self._save(rev)

    async def bump_stable(self, revision_id):
        old = self.revisions[revision_id]
        old.stable_polls += 1
        return old

    async def mark_settled(self, revision_id, settled_at):
        old = self.revisions[revision_id]
        old.settled_at = settled_at
        return old

    async def set_status(self, revision_id, status):
        old = self.revisions[revision_id]
        old.status = status
        return old

    async def delete(self, revision_id):
        return self.revisions.pop(revision_id, None) is not None


def make_service(values, parsed, *, published=None, published_entries=None,
                 last_hash=None, require_confirmation=False):
    client = FakeSheetsClient(values)
    rev_service = FakeRevisionService()
    if published is not None:
        rev_service.seed(published, published_entries)
    notifier = FakeNotifier()
    service = DetectionService(
        client,
        FakeParser(parsed),
        FakeSettingsService(require_confirmation),
        FakeSheetsService(last_hash),
        rev_service,
        notifier,
        AppConfig(),
        FakeTiming(),
    )
    return service, rev_service, notifier


def grid(*data_rows):
    return [[MARKER], *data_rows]


def test_new_revision_auto_approved():
    asyncio.run(_test_new_revision_auto_approved())


async def _test_new_revision_auto_approved():
    values = grid(["row"])
    parsed = ParsedTimetable(entries=[_entry("Математика")])
    service, revs, notifier = make_service(values, parsed)

    rev = await service.poll_day(FOR_DATE)

    assert rev is not None
    assert rev.status == "approved"
    assert rev.kind == "new"
    assert notifier.approvals == []
    assert await service.poll_day(FOR_DATE) is None


def test_edit_settles_after_stable_polls():
    asyncio.run(_test_edit_settles_after_stable_polls())


async def _test_edit_settles_after_stable_polls():
    values = grid(["changed"])
    content_hash = _grid_hash(values)
    published = _revision(
        1, "published", header=_normalize_cell(MARKER), content_hash="old"
    )
    parsed = ParsedTimetable(entries=[_entry("Физика")])
    service, revs, _ = make_service(
        values, parsed, published=published,
        published_entries=[_lesson("Математика")],
    )

    assert await service.poll_day(FOR_DATE) is None
    settling = next(
        r for r in revs.revisions.values() if r.status == "settling"
    )
    assert settling.id != 1
    assert settling.kind == "edit"
    assert settling.content_hash == content_hash

    assert await service.poll_day(FOR_DATE) is None
    assert settling.stable_polls == 1
    approved = await service.poll_day(FOR_DATE)
    assert approved is not None
    assert approved.status == "approved"


def test_refresh_resets_stable_polls():
    asyncio.run(_test_refresh_resets_stable_polls())


async def _test_refresh_resets_stable_polls():
    first = grid(["v1"])
    second = grid(["v2"])
    published = _revision(
        1, "published", header=_normalize_cell(MARKER), content_hash="old"
    )
    parsed1 = ParsedTimetable(entries=[_entry("Физика")])
    parsed2 = ParsedTimetable(entries=[_entry("Химия")])
    service, revs, _ = make_service(
        first, parsed1, published=published,
        published_entries=[_lesson("Математика")],
    )

    assert await service.poll_day(FOR_DATE) is None
    assert await service.poll_day(FOR_DATE) is None
    settling = next(r for r in revs.revisions.values() if r.status == "settling")
    assert settling.stable_polls == 1

    service.sheets_client.values = second
    service.parser.parsed = parsed2
    assert await service.poll_day(FOR_DATE) is None
    settling = next(r for r in revs.revisions.values() if r.status == "settling")
    assert settling.stable_polls == 0
    assert settling.content_hash == _grid_hash(second)


def test_revert_to_published_deletes_candidate():
    asyncio.run(_test_revert_to_published_deletes_candidate())


async def _test_revert_to_published_deletes_candidate():
    values = grid(["v1"])
    published = _revision(
        1, "published", header=_normalize_cell(MARKER),
        content_hash=_grid_hash(values),
    )
    service, revs, _ = make_service(
        grid(["other"]), ParsedTimetable(entries=[_entry("Физика")]),
        published=published, published_entries=[_lesson("Математика")],
    )
    revs.seed(_revision(2, "settling", content_hash="cand"))
    service.sheets_client.values = values

    assert await service.poll_day(FOR_DATE) is None
    assert all(r.status == "published" for r in revs.revisions.values())


def test_insane_document_skipped():
    asyncio.run(_test_insane_document_skipped())


async def _test_insane_document_skipped():
    service, revs, _ = make_service(
        grid(["x"]), ParsedTimetable(entries=[]),
    )
    assert await service.poll_day(FOR_DATE) is None
    assert revs.revisions == {}
    assert await service.poll_day(FOR_DATE) is None


def test_require_confirmation_goes_to_pending():
    asyncio.run(_test_require_confirmation_goes_to_pending())


async def _test_require_confirmation_goes_to_pending():
    parsed = ParsedTimetable(entries=[_entry("Математика")])
    service, revs, notifier = make_service(
        grid(["row"]), parsed, require_confirmation=True,
    )
    assert await service.poll_day(FOR_DATE) is None
    rev = next(iter(revs.revisions.values()))
    assert rev.status == "pending_approval"
    assert len(notifier.approvals) == 1


def test_header_text_change_with_same_date_is_edit_not_new():
    asyncio.run(_test_header_text_change_with_same_date_is_edit_not_new())


async def _test_header_text_change_with_same_date_is_edit_not_new():
    published = _revision(
        1, "published", header=f"{MARKER} (изм.)", content_hash="old"
    )
    parsed = ParsedTimetable(entries=[_entry("Физика")])
    service, revs, _ = make_service(
        grid(["changed"]), parsed, published=published,
        published_entries=[_lesson("Математика")],
    )

    assert await service.poll_day(FOR_DATE) is None
    settling = next(r for r in revs.revisions.values() if r.status == "settling")
    assert settling.kind == "edit"
    assert settling.changed_groups == [2124]
