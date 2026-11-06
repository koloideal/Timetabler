from datetime import date

from timetabler.application.services.lesson_timing import LessonTimingResolver
from timetabler.domain.schemas import ParsedTimetable, TimetableEntry
from timetabler.infrastructure.config.app import AppConfig
from timetabler.presentation.messages.timetable_text import (
    note_blocks,
    schedule_table,
)

CFG = AppConfig()
D = date(2026, 11, 4)


def e(pos, subject="Предмет", teacher=None, aud=None, t=None, sg=None, gid=2124):
    return TimetableEntry(
        group_id=gid, date=D, position=pos, subject=subject, teacher=teacher,
        audience=aud, starts_at=t and __import__('datetime').time(*t), subgroup=sg,
    )


def resolved(entries):
    p = ParsedTimetable(entries=entries)
    p.resolved = LessonTimingResolver(CFG.lesson_timing).resolve(p, D)
    return p.resolved


def texts(table):
    def txt(t):
        if isinstance(t, str):
            return t
        if isinstance(t, list):
            return ''.join(x if isinstance(x, str) else x.text for x in t)
        return t.text if hasattr(t, 'text') else str(t)
    return [[txt(c.text) for c in row] for row in table.cells]


def test_split_group_all_mode():
    lessons = resolved([
        e(1, "Защита", "Трус"),
        e(2, "Конструирование", "Винник", "36", (13, 20), 1),
        e(3, "Иностранный", "Соколовский", None, (10, 45), 1),
        e(3, "Иностранный", "Шавейко", "39", (10, 45), 2),
        e(4, "Техника", "Томило"),
    ])
    rows = texts(schedule_table(lessons, "31", CFG, "a", True))
    numbers = [r[0] for r in rows[1:] if r[0]]
    assert numbers == ['1', '2', '3', '4']
    assert any(r[1].startswith('1 п/г') for r in rows)
    assert any(r[1].startswith('2 п/г') for r in rows)
    assert rows[1][2] == '31 · 09:00-10:35'
    assert all('-' in r[2] or r[2] in ('', '—') for r in rows[1:])


def test_split_group_single_subgroup_mode():
    lessons = resolved([
        e(1, "Защита", "Трус"),
        e(2, "Конструирование", "Винник", "36", (13, 20), 1),
        e(3, "Иностранный", "Соколовский", None, (10, 45), 1),
    ])
    rows = texts(schedule_table(lessons, "31", CFG, "1", True))
    assert [r[0] for r in rows[1:]] == ['1', '2', '3']
    assert rows[2][2] == '10:45-12:20' or rows[2][2].endswith('10:45-12:20')
    assert rows[3][2] == '36 · 13:20-14:55'


def test_note_blocks_placement():
    bottom = note_blocks("Обновлено в 10:00")
    top = note_blocks("Обновлено в 10:00", top=True)
    assert type(bottom[0]).__name__ == "InputRichBlockDivider"
    assert type(bottom[1]).__name__ == "InputRichBlockParagraph"
    assert type(top[0]).__name__ == "InputRichBlockParagraph"
    assert type(top[1]).__name__ == "InputRichBlockDivider"


def test_nonsplit_group_subgroup_mode_not_empty():
    lessons = resolved([e(1, "Экономика", "Лобзанюк", gid=1226), e(2, "Менеджмент", gid=1226)])
    for mode in ('a', '1', '2'):
        rows = texts(schedule_table(lessons, None, CFG, mode, True))
        assert len(rows) == 3, mode
        assert rows[1][2] == '09:00-10:35'
