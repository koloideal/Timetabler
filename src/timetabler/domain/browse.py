from collections.abc import Iterable

from timetabler.domain.schemas import DaySchedule, ResolvedLesson


def _all_lessons(day: DaySchedule) -> list[ResolvedLesson]:
    return [l for lessons in day.by_group.values() for l in lessons]


def effective_audience(day: DaySchedule, lesson: ResolvedLesson) -> str | None:
    if lesson.kind == "pe":
        return None
    return lesson.audience or day.audiences.get(lesson.group_id)


def day_teachers(day: DaySchedule) -> list[str]:
    return sorted(
        {l.teacher for l in _all_lessons(day) if l.teacher},
        key=str.lower,
    )


def day_audiences(day: DaySchedule) -> list[str]:
    auds = {effective_audience(day, l) for l in _all_lessons(day)}
    return sorted(
        (a for a in auds if a),
        key=lambda s: (not s.isdigit(), int(s) if s.isdigit() else 0, s),
    )


def _uniq_sorted(lessons: Iterable[ResolvedLesson]) -> list[ResolvedLesson]:
    out: list[ResolvedLesson] = []
    seen: set[tuple] = set()
    for l in sorted(
        lessons,
        key=lambda l: (l.start is None, l.start or 0, l.ordinal, l.group_id),
    ):
        key = (l.group_id, l.position, l.subject, l.teacher, l.audience, l.start, l.end)
        if key in seen:
            continue
        seen.add(key)
        out.append(l)
    return out


def lessons_for_teacher(day: DaySchedule, teacher: str) -> list[ResolvedLesson]:
    return _uniq_sorted(l for l in _all_lessons(day) if l.teacher == teacher)


def lessons_for_audience(day: DaySchedule, audience: str) -> list[ResolvedLesson]:
    return _uniq_sorted(
        l for l in _all_lessons(day) if effective_audience(day, l) == audience
    )
