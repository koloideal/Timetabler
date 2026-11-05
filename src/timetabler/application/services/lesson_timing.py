import logging
import re
from datetime import date

from timetabler.domain.schemas import ParsedTimetable, ResolvedLesson, TimetableEntry
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

    def _is_pe(self, subject: str) -> bool:
        low = subject.lower()
        return any(marker in low for marker in self.config.pe_markers)

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
        occupied: set[int] = set()
        lessons: list[ResolvedLesson] = []
        for e in entries:
            if e.starts_at is not None:
                lessons.append(self._explicit(group_id, for_date, subgroup, e, slots, occupied))
        for e in entries:
            if e.starts_at is None:
                lessons.append(self._untimed(group_id, for_date, subgroup, e, slots, occupied))
        lessons.sort(key=lambda l: (l.start is None, l.start or 0))
        by_slot: dict[int, list[ResolvedLesson]] = {}
        for l in lessons:
            if l.slot is not None:
                by_slot.setdefault(l.slot, []).append(l)
        for slot, group in by_slot.items():
            if len(group) > 1:
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
        occupied: set[int],
    ) -> ResolvedLesson:
        assert entry.starts_at is not None
        weekday = for_date.weekday()
        t = entry.starts_at.hour * 3600 + entry.starts_at.minute * 60 + entry.starts_at.second
        is_pe = self._is_pe(entry.subject)
        for i, slot in enumerate(slots):
            slot_start, slot_end = _slot_seconds(slot)
            half_b = parse_time(slot.half_b_start) if slot.half_b_start else None
            if t == slot_start or (half_b is not None and t == half_b):
                occupied.add(i)
                if is_pe:
                    return self._lesson(
                        group_id, for_date, subgroup, entry, "pe",
                        i + 1, "a" if t == slot_start else "b",
                        t, t + self._half_len(weekday, slot), frozenset(),
                    )
                return self._lesson(
                    group_id, for_date, subgroup, entry, "lesson",
                    i + 1, "full", slot_start, slot_end, frozenset(),
                )
        nominal = slots[entry.position - 1] if entry.position and entry.position <= len(slots) else (slots[-1] if slots else None)
        dur = self._half_len(weekday, nominal) if is_pe and nominal else (
            (_slot_seconds(nominal)[1] - _slot_seconds(nominal)[0]) if nominal else 0
        )
        return self._lesson(
            group_id, for_date, subgroup, entry, "pe" if is_pe else "lesson",
            None, "a" if is_pe else "full", t, t + dur, frozenset({"off_grid"}),
        )

    def _untimed(
        self,
        group_id: int,
        for_date: date,
        subgroup: int | None,
        entry: TimetableEntry,
        slots: tuple[LessonSlotConfig, ...],
        occupied: set[int],
    ) -> ResolvedLesson:
        nominal = (entry.position - 1) if entry.position else -1
        s = nominal if nominal >= 0 else 0
        while s < len(slots) and s in occupied:
            s += 1
        flags: set[str] = set()
        if s >= len(slots) or nominal < 0:
            flags.add("no_slot")
            return self._lesson(
                group_id, for_date, subgroup, entry, "lesson",
                None, "full", None, None, frozenset(flags),
            )
        if s != nominal:
            flags.add("shifted")
        occupied.add(s)
        start, end = _slot_seconds(slots[s])
        return self._lesson(
            group_id, for_date, subgroup, entry, "lesson",
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
