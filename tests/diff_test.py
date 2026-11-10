from datetime import date, time

from timetabler.application.services.detection import compute_diff
from timetabler.domain.schemas import ParsedTimetable, ResolvedLesson

D = date(2026, 11, 10)


def _lesson(
    group=2124, position=1, subgroup=None, subject="Математика",
    teacher="Иванов", audience="204", start=32400, end=38100,
    source_time=None,
) -> ResolvedLesson:
    return ResolvedLesson(
        group_id=group, date=D, position=position, subgroup=subgroup,
        ordinal=position, slot=position, half="full", start=start, end=end,
        kind="lesson", subject=subject, teacher=teacher, audience=audience,
        flags=frozenset(), source_time=source_time,
    )


def _diff(old, new, old_aud=None, new_aud=None):
    parsed = ParsedTimetable(resolved=new, base_audiences=new_aud or {})
    return compute_diff(old, old_aud or {}, parsed)


def test_timing_only_difference_is_not_a_change():
    old = [_lesson(start=32400, end=35100)]
    new = [_lesson(start=32400, end=38100)]
    assert _diff(old, new) == ([], {})


def test_identical_subgroups_equal_whole_group_lesson():
    old = [_lesson(subgroup=None)]
    new = [_lesson(subgroup=1), _lesson(subgroup=2)]
    assert _diff(old, new) == ([], {})
    assert _diff(new, old) == ([], {})


def test_only_really_changed_group_is_reported():
    old = [_lesson(group=2124), _lesson(group=3125, teacher="Петров")]
    new = [_lesson(group=2124, start=1, end=2), _lesson(group=3125, teacher="Сидоров")]
    changed, diff = _diff(old, new)
    assert changed == [3125]
    assert [(l.pos, l.old, l.new) for l in diff[3125]] == [
        ("п.1", "Петров", "Сидоров")
    ]


def test_changes_in_one_lesson_are_a_single_row():
    old = [_lesson(subject="Математика", audience="204")]
    new = [_lesson(subject="Физика", audience="305")]
    _, diff = _diff(old, new)
    assert len(diff[2124]) == 1
    row = diff[2124][0]
    assert row.old == "Математика · ауд. 204"
    assert row.new == "Физика · ауд. 305"


def test_explicit_source_time_change_is_reported():
    old = [_lesson(source_time=time(9, 0))]
    new = [_lesson(source_time=time(9, 30))]
    changed, diff = _diff(old, new)
    assert changed == [2124]
    assert diff[2124][0].old == "09:00" and diff[2124][0].new == "09:30"


def test_whitespace_noise_is_not_a_change():
    old = [_lesson(subject="История  Беларуси")]
    new = [_lesson(subject="История Беларуси")]
    assert _diff(old, new) == ([], {})
