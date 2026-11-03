from datetime import date, time

from timetabler.domain.schemas import TimetableEntry
from timetabler.infrastructure.config.app import AppConfig

_MD_SPECIALS = ("\\", "|", "*", "_", "~", "[", "]", "(", ")")


def _md(text: str) -> str:
    for char in _MD_SPECIALS:
        text = text.replace(char, f"\\{char}")
    return text


def _fmt_time(starts_at: time | None, time_format: str) -> str:
    return starts_at.strftime(time_format) if starts_at else "—"


def _cell(text: str | None) -> str:
    return _md(text) if text else "—"


def format_group_schedule(
    group_label: str,
    base_audience: str | None,
    entries: list[TimetableEntry],
    config: AppConfig,
) -> str:
    lines = [f"### 📚 ГРУППА {_md(group_label)}"]
    if base_audience:
        lines.append(f"> сбор ауд. {_md(base_audience)}")

    lines.append("")
    lines.append("| № | Предмет | Ауд. | Время | Преподаватель |")
    lines.append("|:-:|:--------|:----:|:-----:|:--------------|")

    ordered = sorted(entries, key=lambda e: (e.position is None, e.position or 0, e.subgroup or 0))
    for entry in ordered:
        if entry.position is None:
            position = "–"
        elif entry.subgroup is None:
            position = str(entry.position)
        else:
            position = f"{entry.position}.{entry.subgroup}"

        audience = entry.audience or base_audience
        lines.append(
            f"| **{position}** | {_cell(entry.subject)} | {_cell(audience)} "
            f"| {_fmt_time(entry.starts_at, config.time_format)} | {_cell(entry.teacher)} |"
        )

    return "\n".join(lines)


def build_broadcast_message(
    for_date: date,
    parts: list[str],
    config: AppConfig,
) -> str:
    weekday = config.weekdays_short[for_date.weekday()]
    header = f"**📅 РАСПИСАНИЕ НА {for_date.strftime('%d.%m.%Y')} ({weekday})**"
    body = "\n\n---\n\n".join(parts)
    return f"{header}\n\n{body}" if body else header
