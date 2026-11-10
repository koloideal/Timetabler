from datetime import date, datetime, timezone

from timetabler.domain.schemas import DiffLine, PublishReport, Revision
from timetabler.infrastructure.config.app import AppConfig
from timetabler.presentation.messages import error_text, revision_report_blocks


def _report(kind="edit", **kw) -> PublishReport:
    rev = Revision(
        id=7, for_date=date(2026, 11, 10), weekday=1, header="ШАПКА", content_hash="h",
        group_hashes={}, base_audiences={}, kind=kind, changed_groups=[2124, 3125],
        diff={2124: [DiffLine("п.1", "А", "Б")]} if kind == "edit" else {},
        parent_revision_id=None, status="approved", stable_polls=0,
        detected_at=datetime.now(timezone.utc), settled_at=None, published_at=None,
    )
    base = dict(
        revision=rev, seconds=1.5, age_seconds=42, channels=(1, 0), chats=(1, 0),
        users=(8, 1),
    )
    base.update(kw)
    return PublishReport(**base)


def _texts(blocks):
    return " ".join(str(b) for b in blocks)


def test_report_for_new_schedule_has_day_stats_and_composition():
    blocks = revision_report_blocks(_report("new"), AppConfig())
    text = _texts(blocks)
    assert "Новое расписание" in text and "10.11.2026" in text
    assert "каналов 1, чатов 1, юзеров 8" in text
    assert "ошибок" in text.lower()
    assert "Состав" not in text and "Details" not in text
    assert "📅 День:" in text and "🎓 Группы:" in text and "📬 Доставлено:" in text


def test_report_for_edit_contains_diff():
    text = _texts(revision_report_blocks(_report("edit"), AppConfig()))
    assert "Расписание обновлено" in text and "Группа 2124" in text


def test_error_text_is_escaped_and_truncated():
    text = error_text("Ошибка <x>", "<script>" + "я" * 5000)
    assert "&lt;script&gt;" in text and "<script>" not in text
    assert len(text) < 800 and text.endswith("…</code>")
