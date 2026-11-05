from datetime import date, time

from timetabler.application.services.lesson_timing import (
    LessonTimingResolver, format_range,
)
from timetabler.domain.schemas import ParsedTimetable, TimetableEntry
from timetabler.infrastructure.config.app import LessonTimingConfig

MON = date(2026, 11, 2)  # понедельник
SAT = date(2026, 11, 7)  # суббота


def e(pos, subject="Предмет", teacher=None, aud=None, t=None, sg=None):
    return TimetableEntry(
        group_id=1, date=MON, position=pos, subject=subject,
        teacher=teacher, audience=aud,
        starts_at=time(*t) if t else None, subgroup=sg,
    )


def resolve(entries, for_date=MON):
    parsed = ParsedTimetable(entries=entries)
    return LessonTimingResolver(LessonTimingConfig()).resolve(parsed, for_date)


def test_subgroup_order_swap_2124():
    lessons = resolve([
        e(1, "Защита населения", "Трус Е.А."),
        e(2, "Конструирование программ", "Винник Р.А.", "36", (13, 20), 1),
        e(3, "Иностранный язык", "Соколовский Ю.И.", None, (10, 45), 1),
        e(3, "Иностранный язык", "Шавейко А.В.", "39", (10, 45), 2),
    ])
    s1 = sorted([l for l in lessons if l.subgroup == 1], key=lambda l: l.ordinal)
    assert [l.slot for l in s1] == [1, 2, 3]
    assert [l.position for l in s1] == [1, 3, 2]
    s2 = sorted([l for l in lessons if l.subgroup == 2], key=lambda l: l.ordinal)
    s2_pos3 = next(l for l in s2 if l.position == 3)
    assert s2_pos3.teacher == "Шавейко А.В." and s2_pos3.slot == 2


def test_1226_sub2_pair1_at_1650():
    lessons = resolve([
        e(1, t=(16, 50), sg=2), e(2, sg=2), e(3, sg=2), e(4, sg=2),
    ])
    s2 = sorted(lessons, key=lambda l: l.ordinal)
    assert [(l.position, l.slot) for l in s2] == [(2, 2), (3, 3), (4, 4), (1, 5)]
    assert all(not l.flags for l in s2)


def test_pe_halves_and_full():
    lessons = resolve([
        e(1, "Физическая культура", t=(9, 0)),
        e(2, "Физическая культура", t=(9, 50)),
        e(3, "Физическая культура", t=(14, 10)),
        e(4, "Физическая культура"),
    ])
    by_pos = {l.position: l for l in lessons}
    assert by_pos[1].half == "a" and by_pos[1].end - by_pos[1].start == 2700
    assert by_pos[2].half == "b" and format_range(by_pos[2].start, by_pos[2].end) == "09:50-10:35"
    assert by_pos[3].half == "b" and by_pos[3].slot == 3
    assert by_pos[4].half == "full" and format_range(by_pos[4].start, by_pos[4].end) == "15:05-16:40"


def test_shift_on_collision():
    lessons = resolve([e(1, t=(10, 45), sg=1)] + [e(p, sg=1) for p in (2, 3, 4)])
    by_pos = {l.position: l for l in lessons}
    assert by_pos[1].slot == 2 and not by_pos[1].flags
    assert [by_pos[p].slot for p in (2, 3, 4)] == [3, 4, 5]
    assert all("shifted" in by_pos[p].flags for p in (2, 3, 4))


def test_off_grid_and_no_slot():
    lessons = resolve([
        e(1, t=(9, 0)), e(2, t=(10, 45)), e(3, t=(13, 20)),
        e(4, t=(15, 5)), e(5, t=(16, 50)), e(6), e(2, t=(11, 0)),
    ])
    by_pos = {l.position: l for l in lessons if "no_slot" in l.flags}
    assert len(by_pos) == 1 and by_pos[6].slot is None and by_pos[6].start is None
    off = [l for l in lessons if "off_grid" in l.flags]
    assert len(off) == 1 and off[0].slot is None and off[0].end - off[0].start == 5700


def test_saturday_grid():
    lessons = resolve([
        e(1, "Физическая культура", t=(9, 0)),
        e(2), e(3), e(4),
    ], for_date=SAT)
    by_pos = {l.position: l for l in lessons}
    assert format_range(by_pos[1].start, by_pos[1].end) == "09:00-09:43"
    assert by_pos[2].slot == 2 and by_pos[3].slot == 3
    assert "no_slot" in by_pos[4].flags
