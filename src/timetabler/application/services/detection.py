import hashlib
import logging
import re
from datetime import date, datetime, timedelta, timezone

import orjson

from timetabler.application.ports import CreatorNotifier, ScheduleParser
from timetabler.application.services.lesson_timing import LessonTimingResolver, format_range
from timetabler.application.services.revision import RevisionService
from timetabler.application.services.settings import SettingsService
from timetabler.application.services.sheets import SheetsService
from timetabler.domain.schemas import (
    DiffLine,
    ParsedTimetable,
    Revision,
    TimetableEntry,
)
from timetabler.infrastructure.config.app import AppConfig
from timetabler.infrastructure.sheets import GoogleSheetsClient

def _normalize_cell(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value).strip())
    return re.sub(r"^(-?\d+)\.0+$", r"\1", text)


def _normalize_grid(values: list[list[object]]) -> list[list[str]]:
    rows = []
    for row in values:
        cells = [_normalize_cell(c) for c in row]
        while cells and cells[-1] == "":
            cells.pop()
        if cells:
            rows.append(cells)
    return rows


def _grid_hash(values: list[list[object]]) -> str:
    return hashlib.sha256(orjson.dumps(_normalize_grid(values))).hexdigest()


def _group_hash(entries: list) -> str:
    rows = [
        [getattr(e, "ordinal", None), e.position, e.subgroup,
         getattr(e, "slot", None), getattr(e, "half", None),
         getattr(e, "start", None), getattr(e, "end", None),
         e.subject, e.teacher, e.audience]
        for e in sorted(
            entries, key=lambda e: (e.position is None, e.position or 0, e.subgroup or 0)
        )
    ]
    return hashlib.sha256(orjson.dumps(rows)).hexdigest()


def _entry_key(entry) -> tuple:
    return (entry.position, entry.subgroup)


def _a1_indexes(ref: str) -> tuple[int, int] | None:
    m = re.fullmatch(r"([A-Za-z]+)(\d+)", ref)
    if not m:
        return None
    col = 0
    for ch in m.group(1).upper():
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return int(m.group(2)) - 1, col - 1


def _cell_in_grid(
    values: list[list[object]], a1_range: str, cell: str
) -> object | None:
    bounds = re.fullmatch(r"([A-Za-z]+\d+):([A-Za-z]+\d+)", a1_range)
    if not bounds:
        return None
    r0 = _a1_indexes(bounds.group(1))
    r1 = _a1_indexes(bounds.group(2))
    target = _a1_indexes(cell)
    if not r0 or not r1 or target is None:
        return None
    row, col = target
    if not (r0[0] <= row <= r1[0] and r0[1] <= col <= r1[1]):
        return None
    try:
        return values[row - r0[0]][col - r0[1]]
    except IndexError:
        return None


def parse_header_date(marker: str, formats: tuple[str, ...]) -> date | None:
    for candidate in re.findall(r"\d{1,4}[.\-/]\d{1,2}[.\-/]\d{1,4}", marker):
        for fmt in formats:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def _entry_changes(old, new) -> list[tuple[str, str | None, str | None]]:
    changes = []
    for field, label in (
        ("subject", "предмет"),
        ("teacher", "препод"),
        ("audience", "ауд."),
    ):
        old_v = getattr(old, field)
        new_v = getattr(new, field)
        if old_v != new_v:
            changes.append((label, old_v, new_v))
    old_t = format_range(getattr(old, "start", None), getattr(old, "end", None))
    new_t = format_range(getattr(new, "start", None), getattr(new, "end", None))
    if old_t != new_t:
        changes.append(("время", old_t, new_t))
    return changes


def _pos_label(entry: TimetableEntry) -> str:
    label = "–" if entry.position is None else f"п.{entry.position}"
    if entry.subgroup:
        label += f"/{entry.subgroup}п"
    return label


def compute_diff(
    old_entries: list,
    old_audiences: dict[int, str],
    parsed: ParsedTimetable,
) -> tuple[list[int], dict[int, list[DiffLine]]]:
    old_by_group: dict[int, list] = {}
    for e in old_entries:
        old_by_group.setdefault(e.group_id, []).append(e)
    new_by_group: dict[int, list] = {}
    for e in parsed.resolved or parsed.entries:
        new_by_group.setdefault(e.group_id, []).append(e)

    diff: dict[int, list[DiffLine]] = {}
    for group_id in sorted(set(old_by_group) | set(new_by_group)):
        lines: list[DiffLine] = []
        old_g = old_by_group.get(group_id)
        new_g = new_by_group.get(group_id)
        if old_g is None and new_g is not None:
            lines.append(DiffLine("вся группа", "", None, f"{len(new_g)} пар"))
        elif new_g is None and old_g is not None:
            lines.append(DiffLine("вся группа", "", f"{len(old_g)} пар", None))
        elif old_g is not None and new_g is not None:
            old_map: dict[tuple, list] = {}
            for e in old_g:
                old_map.setdefault(_entry_key(e), []).append(e)
            new_map: dict[tuple, list] = {}
            for e in new_g:
                new_map.setdefault(_entry_key(e), []).append(e)
            key_order = lambda k: (k[0] is None, k[0] or 0, k[1] or 0)
            by_subject = lambda e: (e.subject or "", e.teacher or "", e.audience or "")
            for key in sorted(set(old_map) | set(new_map), key=key_order):
                olds = sorted(old_map.get(key, []), key=by_subject)
                news = sorted(new_map.get(key, []), key=by_subject)
                for old_e, new_e in zip(olds, news):
                    for field, old_v, new_v in _entry_changes(old_e, new_e):
                        lines.append(
                            DiffLine(_pos_label(new_e), field, old_v, new_v)
                        )
                for e in olds[len(news):]:
                    lines.append(DiffLine(_pos_label(e), "пара", e.subject, None))
                for e in news[len(olds):]:
                    lines.append(DiffLine(_pos_label(e), "пара", None, e.subject))
            old_aud = old_audiences.get(group_id)
            new_aud = parsed.base_audiences.get(group_id)
            if old_aud != new_aud:
                lines.append(DiffLine("сбор", "ауд.", old_aud, new_aud))
        if lines:
            diff[group_id] = lines
    return sorted(diff), diff


def new_groups_diff(parsed: ParsedTimetable) -> dict[int, list[DiffLine]]:
    counts: dict[int, int] = {}
    for e in parsed.entries:
        counts[e.group_id] = counts.get(e.group_id, 0) + 1
    return {
        g: [DiffLine("вся группа", "", None, f"{n} пар")]
        for g, n in sorted(counts.items())
    }


class DetectionService:
    def __init__(
        self,
        sheets_client: GoogleSheetsClient,
        parser: ScheduleParser,
        settings_service: SettingsService,
        sheets_service: SheetsService,
        revision_service: RevisionService,
        notifier: CreatorNotifier,
        config: AppConfig,
        timing: LessonTimingResolver,
    ) -> None:
        self.sheets_client = sheets_client
        self.parser = parser
        self.settings_service = settings_service
        self.sheets_service = sheets_service
        self.revision_service = revision_service
        self.notifier = notifier
        self.config = config
        self.timing = timing
        self._logger = logging.getLogger(__name__)
        self._insane_hashes: set[str] = set()

    async def poll_day(self, for_date: date) -> Revision | None:
        weekday = for_date.weekday()
        source = await self.sheets_service.get_source(weekday)
        if not source or not source.spreadsheet_id:
            return None

        settings = await self.settings_service.get_sheets_settings()
        values = await self.sheets_client.read_values(
            source.spreadsheet_id, settings.schedule_range
        )
        content_hash = _grid_hash(values)

        settling = await self.revision_service.get_settling(for_date)
        if content_hash == source.last_hash:
            if settling is not None:
                return await self._on_stable_poll(settling)
            return None

        published = await self.revision_service.get_published(for_date)
        if (
            settling is not None
            and published is not None
            and content_hash == published.content_hash
        ):
            await self.revision_service.delete(settling.id)
            await self.sheets_service.set_last_hash(weekday, content_hash)
            self._logger.info("Revision candidate %s reverted to published", settling.id)
            return None

        if content_hash in self._insane_hashes:
            if settling is not None and self._settle_elapsed(settling):
                return await self._settle(settling)
            return None

        raw_marker = _cell_in_grid(values, settings.schedule_range, settings.date_cell)
        if raw_marker is None:
            marker = await self._read_marker(source.spreadsheet_id, settings.date_cell)
        else:
            marker = _normalize_cell(raw_marker)
        marker_date = parse_header_date(marker, self.config.date_formats)
        if marker_date != for_date:
            if marker_date is None:
                self._logger.warning(
                    "Cannot parse date in header %r for %s, skipping",
                    marker, for_date,
                )
            else:
                self._logger.info(
                    "Sheet header %r is for %s, not %s — skipping",
                    marker, marker_date, for_date,
                )
            if marker:
                await self.sheets_service.mark_header(weekday, marker)
            if settling is not None and self._settle_elapsed(settling):
                return await self._settle(settling)
            return None

        parsed = self.parser.parse(values, default_date=for_date)
        parsed.resolved = self.timing.resolve(parsed, for_date)
        parent_entries = (
            await self.revision_service.get_entries(published.id) if published else []
        )
        if not self._is_sane(parsed, parent_entries):
            self._insane_hashes.add(content_hash)
            self._logger.warning(
                "Detected insane document for %s (empty or groups dropped), skipping",
                for_date,
            )
            return None

        if settling is not None:
            approved = await self._refresh(settling, parsed, marker, content_hash, published, parent_entries)
        else:
            approved = await self._create(for_date, parsed, marker, content_hash, published, parent_entries)

        await self.sheets_service.set_last_hash(weekday, content_hash)
        if marker:
            await self.sheets_service.mark_header(weekday, marker)
        return approved

    async def _create(
        self,
        for_date: date,
        parsed: ParsedTimetable,
        marker: str,
        content_hash: str,
        published: Revision | None,
        parent_entries: list,
    ) -> Revision | None:
        kind = "new" if published is None or marker != published.header else "edit"
        if kind == "edit":
            assert published is not None
            changed, diff = compute_diff(parent_entries, published.base_audiences, parsed)
            if not changed:
                self._logger.info("Formatting-only change for %s, skipped", for_date)
                return None
        else:
            changed = sorted({e.group_id for e in parsed.entries})
            diff = new_groups_diff(parsed)

        revision = await self.revision_service.create(
            for_date=for_date,
            header=marker or None,
            content_hash=content_hash,
            group_hashes=self._group_hashes(parsed),
            kind=kind,
            changed_groups=changed,
            diff=diff,
            parent_revision_id=published.id if published else None,
            parsed=parsed,
        )
        self._logger.info(
            "Detected %s revision %s for %s", kind, revision.id, for_date
        )
        if kind == "new":
            return await self._settle(revision)
        return None

    async def _refresh(
        self,
        settling: Revision,
        parsed: ParsedTimetable,
        marker: str,
        content_hash: str,
        published: Revision | None,
        parent_entries: list,
    ) -> Revision | None:
        kind = "new" if published is None or marker != published.header else "edit"
        if kind == "edit":
            assert published is not None
            changed, diff = compute_diff(parent_entries, published.base_audiences, parsed)
            if not changed:
                await self.revision_service.delete(settling.id)
                self._logger.info("Revision candidate %s became no-op", settling.id)
                return None
        else:
            changed = sorted({e.group_id for e in parsed.entries})
            diff = new_groups_diff(parsed)

        updated = await self.revision_service.refresh_candidate(
            settling,
            header=marker or None,
            content_hash=content_hash,
            group_hashes=self._group_hashes(parsed),
            kind=kind,
            changed_groups=changed,
            diff=diff,
            parent_revision_id=published.id if published else None,
            parsed=parsed,
        )
        if kind == "new" and updated is not None:
            return await self._settle(updated)
        return None

    def _settle_elapsed(self, revision: Revision) -> bool:
        elapsed = datetime.now(timezone.utc) - revision.detected_at
        return elapsed >= timedelta(
            seconds=self.config.revisions.max_settle_seconds
        )

    async def _on_stable_poll(self, settling: Revision) -> Revision | None:
        rev = await self.revision_service.bump_stable(settling.id)
        if rev is None:
            return None
        if (
            rev.stable_polls >= self.config.revisions.stable_polls
            or self._settle_elapsed(rev)
        ):
            return await self._settle(rev)
        return None

    async def _settle(self, revision: Revision) -> Revision | None:
        rev = await self.revision_service.mark_settled(
            revision.id, datetime.now(timezone.utc)
        )
        return await self._gate(rev or revision)

    async def _gate(self, revision: Revision) -> Revision | None:
        settings = await self.settings_service.get_sheets_settings()
        if settings.require_confirmation:
            rev = await self.revision_service.set_status(revision.id, "pending_approval")
            await self.notifier.ask_revision_approval(rev or revision)
            return None
        return await self.revision_service.set_status(revision.id, "approved")

    def _is_sane(
        self, parsed: ParsedTimetable, parent_entries: list
    ) -> bool:
        if not parsed.entries:
            return False
        if not parent_entries:
            return True
        old_groups = {e.group_id for e in parent_entries}
        new_groups = {e.group_id for e in parsed.entries}
        return len(new_groups) >= len(old_groups) * 2 / 3

    @staticmethod
    def _group_hashes(parsed: ParsedTimetable) -> dict[int, str]:
        by_group: dict[int, list] = {}
        for e in parsed.entries:
            by_group.setdefault(e.group_id, []).append(e)
        return {g: _group_hash(entries) for g, entries in by_group.items()}

    async def _read_marker(self, spreadsheet_id: str, date_cell: str) -> str:
        values: list[list[object]] = await self.sheets_client.read_values(
            spreadsheet_id, date_cell
        )
        if not values or not values[0]:
            return ""
        return _normalize_cell(values[0][0])
