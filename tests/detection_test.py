from datetime import date

from timetabler.application.services.detection import parse_header_date

FORMATS = ("%d.%m.%Y", "%Y-%m-%d")


def test_parse_header_date_typical():
    assert parse_header_date(
        "РАСПИСАНИЕ ЗАНЯТИЙ НА 05.11.2026", FORMATS
    ) == date(2026, 11, 5)


def test_parse_header_date_iso():
    assert parse_header_date("на 2026-11-05", FORMATS) == date(2026, 11, 5)


def test_parse_header_date_no_date():
    assert parse_header_date("РАСПИСАНИЕ ЗАНЯТИЙ", FORMATS) is None
    assert parse_header_date("", FORMATS) is None


def test_parse_header_date_short_year_not_matched():
    assert parse_header_date("на 05.11.26", FORMATS) is None
