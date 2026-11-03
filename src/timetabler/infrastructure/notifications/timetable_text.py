from datetime import date, time

from timetabler.domain.schemas import TimetableEntry
from timetabler.infrastructure.config.app import AppConfig


def _fmt_time(starts_at: time | None) -> str:
    return starts_at.strftime("%H:%M") if starts_at else ""


def build_timetable_header(for_date: date, config: AppConfig) -> str:
    weekday = config.weekdays_short[for_date.weekday()]
    return f"📅 <b>РАСПИСАНИЕ НА {for_date.strftime('%d.%m.%Y')} ({weekday})</b>"


def format_group_schedule(
    group_label: str,
    base_audience: str | None,
    entries: list[TimetableEntry],
    config: AppConfig,
) -> str:
    header = f"ГРУППА {group_label}"
    if base_audience:
        header += f" · сбор {base_audience}"

    lines = [header, config.separator]
    ordered = sorted(entries, key=lambda e: (e.position is None, e.position or 0, e.subgroup or 0))
    for entry in ordered:
        if entry.position is None:
            position = "–"
        elif entry.subgroup is None:
            position = str(entry.position)
        else:
            position = f"{entry.position}.{entry.subgroup}"

        subject_line = f"{position:>2}  {entry.subject}"
        if entry.audience:
            subject_line += f" · {entry.audience}"
        lines.append(subject_line)

        details = []
        if entry.starts_at:
            details.append(f"с {_fmt_time(entry.starts_at)}")
        if entry.teacher:
            details.append(entry.teacher)
        if details:
            lines.append(f"    {' · '.join(details)}")

    lines.append(config.separator)
    return "\n".join(lines)


def build_broadcast_message(
    for_date: date,
    parts: list[str],
    config: AppConfig,
) -> str:
    body = "\n\n".join(f"<pre>{part}</pre>" for part in parts)
    return f"{build_timetable_header(for_date, config)}\n\n{body}"
