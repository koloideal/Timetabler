import logging
import re
from datetime import date

from timetabler.domain.schemas import (
    NowStatus,
    ParsedTimetable,
    ResolvedLesson,
    TimetableEntry,
)
from timetabler.infrastructure.config.app import LessonSlotConfig, LessonTimingConfig


def parse_time(text: str) -> int | None:
    m = re.search(r"(\d{1,2})[:.](\d{2})", text)
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60


def _slot_seconds(slot: LessonSlotConfig) -> tuple[int, int]:
    return parse_time(slot.start) or 0, parse_time(slot.end) or 0


def format_time(seconds: int) -> str:
    return f"{seconds // 3600:02}:{seconds % 3600 // 60:02}"


def format_time_ceil(seconds: int) -> str:
    return format_time(-(-seconds // 60) * 60)


def format_range(start: int | None, end: int | None) -> str:
    if start is None or end is None:
        return "—"
    return f"{format_time(start)}-{format_time_ceil(end)}"


def _events(
    lessons: list[ResolvedLesson],
) -> list[tuple[int, int, list[str], int | None]]:
    merged: dict[tuple[int, int], tuple[list[str], int | None]] = {}
    for l in lessons:
        if l.start is None or l.end is None:
            continue
        key = (l.start, l.end)
        subjects, slot = merged.get(key, ([], l.slot))
        if l.subject not in subjects:
            subjects.append(l.subject)
        if slot is None:
            slot = l.slot
        merged[key] = (subjects, slot)
    return [
        (s, e, subjects, slot)
        for (s, e), (subjects, slot) in sorted(merged.items())
    ]


def now_status(lessons: list[ResolvedLesson], now_sec: int) -> NowStatus:
    events = _events(lessons)
    if not events:
        return NowStatus(kind="empty")
    last_end = max(e for _, e, _, _ in events)
    nxt = next((ev for ev in events if ev[0] > now_sec), None)
    current = [ev for ev in events if ev[0] <= now_sec < ev[1]]
    if current:
        slots = [ev[3] for ev in current if ev[3] is not None]
        return NowStatus(
            kind="lesson",
            current_subjects=[s for ev in current for s in ev[2]],
            current_slot=min(slots) if slots else None,
            current_end=max(ev[1] for ev in current),
            next_subjects=nxt[2] if nxt else [],
            next_slot=nxt[3] if nxt else None,
            next_start=nxt[0] if nxt else None,
            last_end=last_end,
        )
    if nxt:
        kind = "before" if now_sec < events[0][0] else "break"
        return NowStatus(
            kind=kind,
            next_subjects=nxt[2],
            next_slot=nxt[3],
            next_start=nxt[0],
            last_end=last_end,
        )
    return NowStatus(kind="done")


def first_event(lessons: list[ResolvedLesson]) -> tuple[int, list[str]] | None:
    events = _events(lessons)
    if not events:
        return None
    start, _, subjects, _ = events[0]
    return start, subjects


class LessonTimingResolver:
    def __init__(self, config: LessonTimingConfig) -> None:
        self.config = config
        self._logger = logging.getLogger(__name__)

    def resolve(self, parsed: ParsedTimetable, for_date: date) -> list[ResolvedLesson]:
        slots = self.config.weekday_slots[for_date.weekday()]
        by_group: dict[int, list[TimetableEntry]] = {}
        for e in parsed.entries:
            by_group.setdefault(e.group_id, []).append(e)
        out: list[ResolvedLesson] = []
        for group_id, entries in by_group.items():
            out += self._resolve_group(group_id, for_date, entries, slots)
        return out

    def _kind(self, subject: str) -> str:
        low = subject.lower()
        if any(marker in low for marker in self.config.pe_markers):
            return "pe"
        if any(marker in low for marker in self.config.kur_markers):
            return "kur"
        return "lesson"

    def _half_len(self, weekday: int, slot: LessonSlotConfig) -> int:
        half_len = self.config.half_len[weekday]
        if half_len is not None:
            return half_len
        start, end = _slot_seconds(slot)
        return (end - start) // 2

    def _resolve_group(
        self,
        group_id: int,
        for_date: date,
        entries: list[TimetableEntry],
        slots: tuple[LessonSlotConfig, ...],
    ) -> list[ResolvedLesson]:
        if any(e.subgroup is not None for e in entries):
            timelines: dict[int | None, list[TimetableEntry]] = {
                1: [e for e in entries if e.subgroup in (1, None)],
                2: [e for e in entries if e.subgroup in (2, None)],
            }
        else:
            timelines = {None: list(entries)}
        out: list[ResolvedLesson] = []
        for subgroup, timeline in timelines.items():
            out += self._resolve_timeline(group_id, for_date, subgroup, timeline, slots)
        return out

    def _resolve_timeline(
        self,
        group_id: int,
        for_date: date,
        subgroup: int | None,
        entries: list[TimetableEntry],
        slots: tuple[LessonSlotConfig, ...],
    ) -> list[ResolvedLesson]:
        full_slots: set[int] = set()
        taken_halves: dict[int, set[str]] = {}
        half_partners: dict[int, int] = {}
        for e in entries:
            if self._kind(e.subject) != "lesson":
                nominal = (e.position - 1) if e.position else -1
                half_partners[nominal] = half_partners.get(nominal, 0) + 1
        lessons: list[ResolvedLesson] = []
        for e in entries:
            if e.starts_at is not None:
                lessons.append(
                    self._explicit(
                        group_id, for_date, subgroup, e, slots,
                        full_slots, taken_halves,
                    )
                )
        for e in entries:
            if e.starts_at is None:
                lessons.append(
                    self._untimed(
                        group_id, for_date, subgroup, e, slots,
                        full_slots, taken_halves, half_partners,
                    )
                )
        lessons.sort(key=lambda l: (l.start is None, l.start or 0))
        by_slot: dict[int, list[ResolvedLesson]] = {}
        for l in lessons:
            if l.slot is not None and l.start is not None and l.end is not None:
                by_slot.setdefault(l.slot, []).append(l)
        for slot, group in by_slot.items():
            conflicted = any(
                a.start is not None and a.end is not None
                and b.start is not None and b.end is not None
                and a.start < b.end and b.start < a.end
                for i, a in enumerate(group)
                for b in group[i + 1:]
            )
            if conflicted:
                self._logger.warning(
                    "Slot conflict: group %s %s slot %s — %d lessons",
                    group_id, subgroup, slot, len(group),
                )
                for l in group:
                    l.flags = l.flags | {"conflict"}
        for i, l in enumerate(lessons, 1):
            l.ordinal = i
        return lessons

    def _explicit(
        self,
        group_id: int,
        for_date: date,
        subgroup: int | None,
        entry: TimetableEntry,
        slots: tuple[LessonSlotConfig, ...],
        full_slots: set[int],
        taken_halves: dict[int, set[str]],
    ) -> ResolvedLesson:
        if entry.starts_at is None:
            raise RuntimeError("_explicit called with untimed entry")
        weekday = for_date.weekday()
        t = entry.starts_at.hour * 3600 + entry.starts_at.minute * 60 + entry.starts_at.second
        kind = self._kind(entry.subject)
        is_half = kind != "lesson"
        for i, slot in enumerate(slots):
            slot_start, slot_end = _slot_seconds(slot)
            half_b = parse_time(slot.half_b_start) if slot.half_b_start else None
            if t == slot_start or (half_b is not None and t == half_b):
                if is_half:
                    half = "a" if t == slot_start else "b"
                    taken_halves.setdefault(i, set()).add(half)
                    return self._lesson(
                        group_id, for_date, subgroup, entry, kind,
                        i + 1, half,
                        t, t + self._half_len(weekday, slot), frozenset(),
                    )
                full_slots.add(i)
                return self._lesson(
                    group_id, for_date, subgroup, entry, kind,
                    i + 1, "full", slot_start, slot_end, frozenset(),
                )
        nominal = slots[entry.position - 1] if entry.position and entry.position <= len(slots) else (slots[-1] if slots else None)
        dur = self._half_len(weekday, nominal) if is_half and nominal else (
            (_slot_seconds(nominal)[1] - _slot_seconds(nominal)[0]) if nominal else 0
        )
        return self._lesson(
            group_id, for_date, subgroup, entry, kind,
            None, "a" if is_half else "full", t, t + dur, frozenset({"off_grid"}),
        )

    def _untimed(
        self,
        group_id: int,
        for_date: date,
        subgroup: int | None,
        entry: TimetableEntry,
        slots: tuple[LessonSlotConfig, ...],
        full_slots: set[int],
        taken_halves: dict[int, set[str]],
        half_partners: dict[int, int],
    ) -> ResolvedLesson:
        nominal = (entry.position - 1) if entry.position else -1
        s = nominal if nominal >= 0 else 0
        kind = self._kind(entry.subject)
        is_half = kind != "lesson" and half_partners.get(nominal, 0) >= 2
        flags: set[str] = set()
        if is_half:
            while s < len(slots) and (
                s in full_slots or len(taken_halves.get(s, ())) >= 2
            ):
                s += 1
        else:
            while s < len(slots) and (s in full_slots or taken_halves.get(s)):
                s += 1
        if s >= len(slots) or nominal < 0:
            flags.add("no_slot")
            return self._lesson(
                group_id, for_date, subgroup, entry, kind,
                None, "a" if is_half else "full", None, None, frozenset(flags),
            )
        if s != nominal:
            flags.add("shifted")
        start, end = _slot_seconds(slots[s])
        weekday = for_date.weekday()
        if is_half:
            slot = slots[s]
            half = "a" if "a" not in taken_halves.get(s, ()) else "b"
            taken_halves.setdefault(s, set()).add(half)
            half_b = parse_time(slot.half_b_start) if slot.half_b_start else None
            h_start = (
                start if half == "a"
                else half_b or (start + self._half_len(weekday, slot))
            )
            return self._lesson(
                group_id, for_date, subgroup, entry, kind,
                s + 1, half, h_start,
                h_start + self._half_len(weekday, slots[s]),
                frozenset(flags),
            )
        full_slots.add(s)
        return self._lesson(
            group_id, for_date, subgroup, entry, kind,
            s + 1, "full", start, end, frozenset(flags),
        )

    @staticmethod
    def _lesson(
        group_id: int,
        for_date: date,
        subgroup: int | None,
        entry: TimetableEntry,
        kind: str,
        slot: int | None,
        half: str,
        start: int | None,
        end: int | None,
        flags: frozenset[str],
    ) -> ResolvedLesson:
        return ResolvedLesson(
            group_id=group_id,
            date=for_date,
            position=entry.position,
            subgroup=subgroup,
            ordinal=0,
            slot=slot,
            half=half,
            start=start,
            end=end,
            kind=kind,
            subject=entry.subject,
            teacher=entry.teacher,
            audience=entry.audience,
            flags=flags,
            source_time=entry.starts_at,
        )
