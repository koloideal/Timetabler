import hashlib
import logging
import re
from collections import Counter
from dataclasses import dataclass
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


def _a1_indexes(ref: str) -> tuple[int, int] | None:
    m = re.fullmatch(r"([A-Za-z]+)(\d+)", ref)
    if not m:
        return None
    col = 0
    for ch in m.group(1).upper():
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return int(m.group(2)) - 1, col - 1


def _a1_col(idx: int) -> str:
    out = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


def _widened_range(a1_range: str, cell: str) -> str:
    bounds = re.fullmatch(r"([A-Za-z]+\d+):([A-Za-z]+\d+)", a1_range)
    target = _a1_indexes(cell)
    if not bounds or target is None:
        return a1_range
    r0 = _a1_indexes(bounds.group(1))
    r1 = _a1_indexes(bounds.group(2))
    if not r0 or not r1:
        return a1_range
    row0, col0 = min(r0[0], target[0]), min(r0[1], target[1])
    row1, col1 = max(r1[0], target[0]), max(r1[1], target[1])
    return f"{_a1_col(col0)}{row0 + 1}:{_a1_col(col1)}{row1 + 1}"


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
    for match in re.findall(
        r"\d{1,4}\s*[.\-/]\s*\d{1,2}\s*[.\-/]\s*\d{1,4}", marker
    ):
        candidate = re.sub(r"\s+", "", match)
        for fmt in formats:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def _clean(value: object) -> str | None:
    text = " ".join(str(value).split()) if value is not None else ""
    return text or None


def _src(entry) -> tuple[str | None, str | None, str | None, str | None]:
    raw = getattr(entry, "source_time", None)
    if raw is None:
        raw = getattr(entry, "starts_at", None)
    return (
        _clean(entry.subject),
        _clean(entry.teacher),
        _clean(entry.audience),
        raw.strftime("%H:%M") if raw is not None else None,
    )


@dataclass
class _Row:
    position: int | None
    subgroup: int | None
    src: tuple[str | None, str | None, str | None, str | None]
    entry: object


def _canon_rows(entries: list) -> list[_Row]:
    by_pos: dict[int | None, list] = {}
    for e in entries:
        by_pos.setdefault(e.position, []).append(e)
    rows: list[_Row] = []
    for pos, items in by_pos.items():
        sg1 = [e for e in items if e.subgroup == 1]
        sg2 = [e for e in items if e.subgroup == 2]
        merge = bool(sg1) and bool(sg2) and Counter(map(_src, sg1)) == Counter(
            map(_src, sg2)
        )
        for e in items:
            if merge and e.subgroup == 2:
                continue
            sub = None if merge and e.subgroup == 1 else e.subgroup
            rows.append(_Row(pos, sub, _src(e), e))
    return rows


def _signature(rows: list[_Row]) -> Counter:
    return Counter((r.position, r.subgroup, r.src) for r in rows)


def _src_changes(
    old: tuple, new: tuple
) -> list[tuple[str, str | None, str | None]]:
    labels = ("предмет", "препод", "ауд.", "время")
    return [
        (label, o, n) for label, o, n in zip(labels, old, new) if o != n
    ]


def _pos_label(position: int | None, subgroup: int | None) -> str:
    label = "–" if position is None else f"п.{position}"
    if subgroup:
        label += f"/{subgroup}п"
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
            lines.append(DiffLine("вся группа", None, f"{len(new_g)} пар"))
        elif new_g is None and old_g is not None:
            lines.append(DiffLine("вся группа", f"{len(old_g)} пар", None))
        elif old_g is not None and new_g is not None:
            old_rows = _canon_rows(old_g)
            new_rows = _canon_rows(new_g)
            if _signature(old_rows) != _signature(new_rows):
                lines.extend(_row_lines(old_rows, new_rows))
            old_aud = old_audiences.get(group_id)
            new_aud = parsed.base_audiences.get(group_id)
            if old_aud != new_aud:
                lines.append(
                    DiffLine(
                        "сбор",
                        f"ауд. {old_aud}" if old_aud else None,
                        f"ауд. {new_aud}" if new_aud else None,
                    )
                )
        if lines:
            diff[group_id] = lines
    return sorted(diff), diff


def _row_lines(old_rows: list[_Row], new_rows: list[_Row]) -> list[DiffLine]:
    old_map: dict[tuple, list[_Row]] = {}
    for r in old_rows:
        old_map.setdefault((r.position, r.subgroup), []).append(r)
    new_map: dict[tuple, list[_Row]] = {}
    for r in new_rows:
        new_map.setdefault((r.position, r.subgroup), []).append(r)
    key_order = lambda k: (k[0] is None, k[0] or 0, k[1] or 0)
    by_src = lambda r: tuple(x or "" for x in r.src)
    lines: list[DiffLine] = []
    for key in sorted(set(old_map) | set(new_map), key=key_order):
        olds = sorted(old_map.get(key, []), key=by_src)
        news = sorted(new_map.get(key, []), key=by_src)
        label = _pos_label(*key)
        for old_r, new_r in zip(olds, news):
            changes = _src_changes(old_r.src, new_r.src)
            if changes:
                lines.append(
                    DiffLine(
                        label,
                        _changes_side(changes, 0),
                        _changes_side(changes, 1),
                    )
                )
        for r in olds[len(news):]:
            lines.append(DiffLine(label, _lesson_desc(r.entry), None))
        for r in news[len(olds):]:
            lines.append(DiffLine(label, None, _lesson_desc(r.entry)))
    return lines


def _fmt_change_val(label: str, value: object) -> str:
    if value is None:
        return "—"
    return f"ауд. {value}" if label == "ауд." else str(value)


def _changes_side(changes: list[tuple[str, str | None, str | None]], idx: int) -> str:
    return " · ".join(
        _fmt_change_val(label, values[idx]) for label, *values in changes
    )


def _lesson_desc(e) -> str:
    parts = [e.subject or "—"]
    if e.teacher:
        parts.append(e.teacher)
    if e.audience:
        parts.append(f"ауд. {e.audience}")
    if getattr(e, "start", None) is not None:
        parts.append(format_range(e.start, e.end))
    return " · ".join(parts)


def new_groups_diff(parsed: ParsedTimetable) -> dict[int, list[DiffLine]]:
    counts: dict[int, int] = {}
    for e in parsed.entries:
        counts[e.group_id] = counts.get(e.group_id, 0) + 1
    return {
        g: [DiffLine("вся группа", None, f"{n} пар")]
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
        self._events = logging.getLogger("events")
        self._insane_hashes: set[str] = set()
        self._reported: set[tuple] = set()

    async def _report_once(
        self, key: tuple, title: str, details: str = ""
    ) -> None:
        if key in self._reported:
            return
        if len(self._reported) > 500:
            self._reported.clear()
        self._reported.add(key)
        try:
            await self.notifier.notify_error(title, details)
        except Exception:
            self._logger.exception("Cannot send error notice to creator")

    async def poll_day(self, for_date: date) -> Revision | None:
        weekday = for_date.weekday()
        source = await self.sheets_service.get_source(weekday)
        if not source or not source.spreadsheet_id:
            return None

        settings = await self.settings_service.get_sheets_settings()
        fetch_range = _widened_range(settings.schedule_range, settings.date_cell)
        values = await self.sheets_client.read_values(
            source.spreadsheet_id, fetch_range
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
            self._events.info(
                "↩️ Ревизия #%s откатилась к опубликованной — удалена", settling.id
            )
            return None

        if content_hash in self._insane_hashes:
            if settling is not None and self._settle_elapsed(settling):
                return await self._settle(settling)
            return None

        raw_marker = _cell_in_grid(values, fetch_range, settings.date_cell)
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
                await self._report_once(
                    ("header", for_date, marker),
                    f"Не распознана дата в шапке · {for_date:%d.%m.%Y}",
                    f"Ячейка {settings.date_cell}: «{marker}»",
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
        conflicts = sorted(
            {l.group_id for l in parsed.resolved if "conflict" in l.flags}
        )
        if conflicts:
            await self._report_once(
                ("conflict", for_date, content_hash),
                f"Конфликт пар по времени · {for_date:%d.%m.%Y}",
                f"Пересекаются пары в группах: {', '.join(map(str, conflicts))}",
            )
        parent_entries = (
            await self.revision_service.get_entries(published.id) if published else []
        )
        if not self._is_sane(parsed, parent_entries):
            if len(self._insane_hashes) > 500:
                self._insane_hashes.clear()
            self._insane_hashes.add(content_hash)
            self._logger.warning(
                "Detected insane document for %s (empty or groups dropped), skipping",
                for_date,
            )
            old_groups = len({e.group_id for e in parent_entries})
            new_groups = len({e.group_id for e in parsed.entries})
            await self._report_once(
                ("insane", for_date, content_hash),
                f"Подозрительный документ · {for_date:%d.%m.%Y} — пропущен",
                f"Групп в документе: {new_groups}, в опубликованном: {old_groups}"
                if parsed.entries else "В документе не найдено ни одной пары",
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
        kind = "new" if published is None else "edit"
        if kind == "edit":
            if published is None:
                self._logger.error("edit kind without published for %s", for_date)
                await self._report_once(
                    ("nopub", for_date),
                    f"Внутренняя ошибка · {for_date:%d.%m.%Y}",
                    "правка без опубликованной ревизии",
                )
                return None
            changed, diff = compute_diff(parent_entries, published.base_audiences, parsed)
            if not changed:
                self._events.info(
                    "⏭ Правка на %s без реальных изменений в группах — пропущена",
                    for_date.strftime("%d.%m.%Y"),
                )
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
        self._events.info(
            "🔎 Ревизия #%s (%s) на %s обнаружена: изменённые группы %s",
            revision.id, "новое расписание" if kind == "new" else "правка",
            for_date.strftime("%d.%m.%Y"), changed,
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
        kind = "new" if published is None else "edit"
        if kind == "edit":
            if published is None:
                self._logger.error(
                    "edit kind without published for %s", settling.for_date
                )
                return None
            changed, diff = compute_diff(parent_entries, published.base_audiences, parsed)
            if not changed:
                await self.revision_service.delete(settling.id)
                self._events.info(
                    "⏭ Ревизия #%s после доп. правок не меняет расписание — удалена",
                    settling.id,
                )
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
        age = int((datetime.now(timezone.utc) - revision.detected_at).total_seconds())
        if settings.require_confirmation:
            self._events.info(
                "🕓 Ревизия #%s стабильна (%s с после обнаружения) — ждёт подтверждения админа",
                revision.id, age,
            )
            rev = await self.revision_service.set_status(revision.id, "pending_approval")
            await self.notifier.ask_revision_approval(rev or revision)
            return None
        self._events.info(
            "✅ Ревизия #%s стабильна (%s с после обнаружения) — отправляю в рассылку",
            revision.id, age,
        )
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
