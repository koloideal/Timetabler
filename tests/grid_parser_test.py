from datetime import date, time

from timetabler.infrastructure.config.app import AppConfig
from timetabler.infrastructure.parsing.grid_parser import GridScheduleParser

D = date(2026, 11, 14)


def _parser() -> GridScheduleParser:
    return GridScheduleParser(AppConfig())


def test_parse_stops_at_second_schedule_header():
    values = [
        ["РАСПИСАНИЕ ЗАНЯТИЙ НА 14.11.2026"],
        ["Номер группы, ауд."],
        ["2124, ауд. 31", "1.", "Операционные системы", None, "Винник Р.А.", "33"],
        ["", "2.", "Математика", None, "Ванькович Т.В.", None],
        [],
        [" РАСПИСАНИЕ ЗАНЯТИЙ НА 25.01.2024"],
        ["Номер группы, ауд."],
        ["2124, ауд. 23", "1.", "Биология (Трус Н.Н.)"],
        ["куратор", "2.", "Белорусская литература"],
    ]
    parsed = _parser().parse(values, D)
    assert [e.subject for e in parsed.entries] == [
        "Операционные системы",
        "Математика",
    ]
    assert parsed.base_audiences == {2124: "31"}


def test_parse_stops_at_repeated_column_header():
    values = [
        ["2124", "1.", "Математика"],
        ["Номер группы, ауд."],
        ["2124", "2.", "Биология"],
    ]
    parsed = _parser().parse(values, D)
    assert [e.subject for e in parsed.entries] == ["Математика"]


def test_boundary_before_first_group_does_not_stop():
    values = [
        ["РАСПИСАНИЕ ЗАНЯТИЙ НА 14.11.2026"],
        ["(Суббота)"],
        ["Номер группы, ауд."],
        ["2124", "1.", "Математика"],
    ]
    parsed = _parser().parse(values, D)
    assert [e.subject for e in parsed.entries] == ["Математика"]


def test_boundary_case_insensitive():
    values = [
        ["2124", "1.", "Математика"],
        ["расписание занятий на 15.11"],
        ["2124", "2.", "Биология"],
    ]
    parsed = _parser().parse(values, D)
    assert [e.subject for e in parsed.entries] == ["Математика"]


def test_lone_sg2_audience_merges_into_whole_group():
    values = [
        ["2125, ауд. 37", "1.", "Математика", None, "Ванькович Т.В.", None, None, None, "35"],
        ["", "2.", "Охрана труда", None, "Волотовская Т.Е.", None],
    ]
    parsed = _parser().parse(values, D)
    assert [(e.position, e.subgroup, e.teacher, e.audience) for e in parsed.entries] == [
        (1, None, "Ванькович Т.В.", "35"),
        (2, None, "Волотовская Т.Е.", None),
    ]


def test_sg1_audience_wins_over_stray_sg2_audience():
    values = [
        ["2124", "1.", "ОС", None, "Винник Р.А.", "33", None, None, "35"],
    ]
    (e,) = _parser().parse(values, D).entries
    assert (e.subgroup, e.teacher, e.audience) == (None, "Винник Р.А.", "33")


def test_real_sg2_row_stays_sg2():
    values = [
        ["2124", "1.", "ОС", None, None, None, None, "Гордиевич А.Г.", "31"],
    ]
    (e,) = _parser().parse(values, D).entries
    assert (e.subgroup, e.teacher, e.audience) == (2, "Гордиевич А.Г.", "31")


def test_stray_sg1_audience_joins_sg2_row():
    values = [
        ["2124", "1.", "ОС", None, None, "35", None, "Гордиевич А.Г.", None],
    ]
    (e,) = _parser().parse(values, D).entries
    assert (e.subgroup, e.teacher, e.audience) == (2, "Гордиевич А.Г.", "35")


def test_sg2_time_only_counts_as_lesson():
    values = [
        ["2124", "1.", "ОС", None, "Винник Р.А.", "33", "13:00", None, "31"],
    ]
    entries = _parser().parse(values, D).entries
    assert {(e.subgroup, e.starts_at) for e in entries} == {
        (1, None),
        (2, time(13, 0)),
    }


def test_normal_rows_still_parse():
    values = [
        ["2124, ауд. 31", "1.", "ОС", None, "Винник Р.А.", "33", None, "Гордиевич А.Г.", "31"],
        ["", "2.", "Математика", None, "Ванькович Т.В.", None],
        ["3125, ауд. 8", "1.", "Делопроизводство", None, "Романцевич Д.А.", None],
    ]
    parsed = _parser().parse(values, D)
    by_sg = {(e.position, e.subgroup) for e in parsed.entries}
    assert (1, 1) in by_sg and (1, 2) in by_sg and (2, None) in by_sg
    assert {e.group_id for e in parsed.entries} == {2124, 3125}
    assert parsed.base_audiences == {2124: "31", 3125: "8"}


def test_latin_subject_ends_document():
    values = [
        ["5125, ауд. 11", "1.", "Астрономия", None, "Гиль Т.В."],
        ["", "4.", "Иностранный язык", None, "Бохан О.А."],
        [""] * 10,
        ["", "", "Material icon theme"],
        ["", "", "jQuery 3.7"],
    ]
    parsed = _parser().parse(values, D)
    assert [e.subject for e in parsed.entries] == ["Астрономия", "Иностранный язык"]


def test_latin_subject_before_first_group_ignored():
    values = [
        ["", "", "scratch note in latin"],
        ["2124", "1.", "Математика"],
    ]
    parsed = _parser().parse(values, D)
    assert [e.subject for e in parsed.entries] == ["Математика"]


def test_mixed_cyrillic_latin_subject_kept():
    values = [
        ["2124", "1.", "СУБД PostgreSQL"],
    ]
    parsed = _parser().parse(values, D)
    assert [e.subject for e in parsed.entries] == ["СУБД PostgreSQL"]


def test_empty_gap_resets_group_context():
    values = [
        ["2123, ауд. 5"],
        ["", "", "ПРАКТИКА"],
        *[[]] * 10,
        ["", "", "Заметка не из расписания"],
        ["3125, ауд. 8", "1.", "Делопроизводство"],
    ]
    parsed = _parser().parse(values, D)
    subjects = [e.subject for e in parsed.entries]
    assert subjects == ["ПРАКТИКА", "Делопроизводство"]
    assert {e.group_id for e in parsed.entries} == {2123, 3125}


def test_short_empty_gap_keeps_context():
    values = [
        ["2124", "1.", "ОС", None, "Винник Р.А."],
        *[[]] * 5,
        ["", "2.", "Математика"],
    ]
    parsed = _parser().parse(values, D)
    assert [e.subject for e in parsed.entries] == ["ОС", "Математика"]
