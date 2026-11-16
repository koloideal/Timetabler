from datetime import date

from timetabler.domain.browse import (
    day_audiences,
    day_teachers,
    lessons_for_audience,
    lessons_for_teacher,
)
from timetabler.domain.schemas import DaySchedule, ResolvedLesson

D = date(2026, 11, 17)


def _lesson(**kw) -> ResolvedLesson:
    base = dict(
        group_id=2124, date=D, position=1, subgroup=None, ordinal=0,
        slot=1, half="full", start=32400, end=36000, kind="lesson",
        subject="ОС", teacher=None, audience=None,
        flags=frozenset(), source_time=None,
    )
    base.update(kw)
    return ResolvedLesson(**base)


def _day(lessons, audiences=None) -> DaySchedule:
    by_group: dict[int, list[ResolvedLesson]] = {}
    for l in lessons:
        by_group.setdefault(l.group_id, []).append(l)
    return DaySchedule(
        by_group=by_group, audiences=audiences or {}, labels={}, split=set()
    )


def test_day_teachers_sorted_and_unique():
    day = _day([
        _lesson(teacher="Яшин А.А."),
        _lesson(teacher="Бобрик А.Г.", position=2),
        _lesson(teacher="бобрик а.г.".title()),
        _lesson(teacher=None, position=3),
    ])
    assert day_teachers(day) == ["Бобрик А.Г.", "Яшин А.А."]


def test_day_audiences_effective_numeric_sort():
    day = _day(
        [
            _lesson(audience="33"),
            _lesson(group_id=2125, position=2),
            _lesson(group_id=2125, position=2, kind="pe"),
            _lesson(group_id=3000, position=1, audience="спортзал"),
        ],
        audiences={2125: "37"},
    )
    assert day_audiences(day) == ["33", "37", "спортзал"]


def test_lessons_for_teacher_dedupes_subgroups():
    day = _day([
        _lesson(teacher="Винник Р.А.", subgroup=1),
        _lesson(teacher="Винник Р.А.", subgroup=2),
        _lesson(teacher="Винник Р.А.", position=3, subject="СУБД", slot=3, start=42000, end=46800),
        _lesson(teacher="Другой П.П.", position=2),
    ])
    lessons = lessons_for_teacher(day, "Винник Р.А.")
    assert [(l.position, l.subject) for l in lessons] == [(1, "ОС"), (3, "СУБД")]


def test_lessons_for_audience_uses_base_audience_and_skips_pe():
    day = _day(
        [
            _lesson(group_id=2125, audience=None),                    # → базовая 37
            _lesson(group_id=2125, position=2, kind="pe"),            # физра — без ауд.
            _lesson(group_id=2124, position=3, audience="37", start=42000, end=46800),  # явная 37
        ],
        audiences={2125: "37"},
    )
    lessons = lessons_for_audience(day, "37")
    assert [(l.group_id, l.position) for l in lessons] == [(2125, 1), (2124, 3)]


def test_browse_render_smoke():
    from timetabler.infrastructure.config.app import AppConfig
    from timetabler.presentation.messages import format_browse_schedule

    day = _day([_lesson(teacher="Винник Р.А.", audience="33")])
    blocks = format_browse_schedule(
        "teacher", "Винник Р.А.", D, lessons_for_teacher(day, "Винник Р.А."), day, AppConfig()
    )
    assert len(blocks) == 2
    assert "Винник Р.А." in str(blocks[0].text)
    aud_blocks = format_browse_schedule(
        "audience", "33", D, lessons_for_audience(day, "33"), day, AppConfig()
    )
    assert "Ауд. 33" in str(aud_blocks[0].text)
