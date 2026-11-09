from datetime import date, time

from timetabler.application.services.lesson_timing import (
    LessonTimingResolver, first_event, format_range, now_status,
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


def test_two_untimed_halves_share_slot():
    lessons = resolve([
        e(1, "Кураторский час"),
        e(1, "Физическая культура"),
        e(2, "Математика"),
    ])
    by_subj = {l.subject: l for l in lessons}
    kur = by_subj["Кураторский час"]
    pe = by_subj["Физическая культура"]
    assert kur.slot == 1 and kur.half == "a"
    assert format_range(kur.start, kur.end) == "09:00-09:45"
    assert pe.slot == 1 and pe.half == "b"
    assert format_range(pe.start, pe.end) == "09:50-10:35"
    assert by_subj["Математика"].slot == 2
    assert all("conflict" not in l.flags for l in lessons)


def test_single_untimed_half_is_full_lesson():
    lessons = resolve([
        e(1, "Физическая культура"),
        e(2, "Математика"),
    ])
    by_subj = {l.subject: l for l in lessons}
    pe = by_subj["Физическая культура"]
    assert pe.slot == 1 and pe.half == "full"
    assert format_range(pe.start, pe.end) == "09:00-10:35"
    assert by_subj["Математика"].slot == 2


def test_explicit_half_plus_untimated_half():
    lessons = resolve([
        e(1, "Кураторский час", t=(9, 0)),
        e(1, "Физическая культура"),
    ])
    by_subj = {l.subject: l for l in lessons}
    kur = by_subj["Кураторский час"]
    pe = by_subj["Физическая культура"]
    assert kur.slot == 1 and kur.half == "a"
    assert pe.slot == 1 and pe.half == "b"
    assert format_range(pe.start, pe.end) == "09:50-10:35"


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


def sec(h, m=0):
    return h * 3600 + m * 60


def test_now_status_lesson_break_done():
    lessons = resolve([e(1, "Математика"), e(2, "Физика")])
    st = now_status(lessons, sec(9, 30))
    assert st.kind == "lesson"
    assert st.current_subjects == ["Математика"] and st.current_slot == 1
    assert st.current_end == sec(10, 35)
    assert st.next_subjects == ["Физика"] and st.next_start == sec(10, 45)
    assert st.last_end == sec(12, 20)

    st = now_status(lessons, sec(10, 40))
    assert st.kind == "break" and st.next_subjects == ["Физика"]

    st = now_status(lessons, sec(13))
    assert st.kind == "done"

    st = now_status(lessons, sec(8))
    assert st.kind == "before" and st.next_start == sec(9)

    assert now_status([], sec(10)).kind == "empty"


def test_now_status_merges_parallel_subgroups():
    lessons = resolve([
        e(3, "Иностранный язык", "Соколовский", None, (10, 45), 1),
        e(3, "Иностранный язык", "Шавейко", "39", (10, 45), 2),
    ])
    st = now_status(lessons, sec(11))
    assert st.kind == "lesson"
    assert st.current_subjects == ["Иностранный язык"]
    assert st.current_end == sec(12, 20)


def test_first_event():
    lessons = resolve([e(2, "Физика"), e(1, "Математика")])
    start, subjects = first_event(lessons)
    assert start == sec(9) and subjects == ["Математика"]
    assert first_event([]) is None


def test_saturday_grid():
    lessons = resolve([
        e(1, "Физическая культура", t=(9, 0)),
        e(2), e(3), e(4),
    ], for_date=SAT)
    by_pos = {l.position: l for l in lessons}
    assert format_range(by_pos[1].start, by_pos[1].end) == "09:00-09:43"
    assert by_pos[2].slot == 2 and by_pos[3].slot == 3
    assert "no_slot" in by_pos[4].flags
