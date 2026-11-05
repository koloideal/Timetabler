from datetime import date, time
from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from timetabler.domain.schemas import TimetableEntry
from timetabler.infrastructure.config.app import AppConfig


def _md(text: str) -> str:
    for char in ("\\", "|", "*", "_", "~", "[", "]", "(", ")"):
        text = text.replace(char, f"\\{char}")
    return text


def _fmt_time(starts_at: time | None, time_format: str) -> str:
    return f"⏰ с {starts_at.strftime(time_format)}" if starts_at else "—"


def _cell(text: str | None) -> str:
    return _md(text) if text else "—"


def _position_label(entry: TimetableEntry) -> str:
    return "–" if entry.position is None else str(entry.position)


def _row(position: str, subject: str, audience: str | None,
         starts_at: time | None, teacher: str | None, config: AppConfig) -> str:
    pos = f"**{position}**" if position else ""
    return (
        f"| {pos} | {_cell(subject)} | {_cell(audience)} "
        f"| {_fmt_time(starts_at, config.time_format)} | {_cell(teacher)} |"
    )


def _entry_row(entry: TimetableEntry, base_audience: str | None, config: AppConfig) -> str:
    return _row(
        _position_label(entry), entry.subject,
        entry.audience or base_audience, entry.starts_at, entry.teacher, config,
    )


def _details_cell(audience: str | None, starts_at: time | None, config: AppConfig) -> str:
    parts = [
        p for p in (
            _md(audience) if audience else None,
            starts_at.strftime(config.time_format) if starts_at else None,
        )
        if p
    ]
    return " · ".join(parts) if parts else "—"


def _crow(position: str, subject: str, details: str) -> str:
    pos = f"**{position}**" if position else ""
    return f"| {pos} | {_cell(subject)} | {details} |"


def _compact_entry_lines(
    entry: TimetableEntry, base_audience: str | None, config: AppConfig
) -> list[str]:
    lines = [
        _crow(
            _position_label(entry), entry.subject,
            _details_cell(entry.audience or base_audience, entry.starts_at, config),
        )
    ]
    if entry.teacher:
        lines.append(f"|  | {_cell(entry.teacher)} |  |")
    return lines


def _pair_blocks(
    entries: list[TimetableEntry], mode: str
) -> list[list[TimetableEntry]]:
    blocks: list[list[TimetableEntry]] = []
    for entry in entries:
        if (
            mode == "a"
            and entry.subgroup is not None
            and blocks
            and blocks[-1][-1].position == entry.position
            and blocks[-1][-1].subject == entry.subject
        ):
            blocks[-1].append(entry)
        elif mode != "a" and entry.subgroup is not None and entry.subgroup != int(mode):
            continue
        else:
            blocks.append([entry])
    return blocks


def format_group_schedule(
    group_label: str,
    base_audience: str | None,
    entries: list[TimetableEntry],
    config: AppConfig,
    mode: str = "a",
    is_compact: bool = False,
) -> str:
    lines = [f"### 🎓 Группа {_md(group_label)}"]
    if base_audience:
        lines.append(f"> сбор ауд. {_md(base_audience)}")

    lines.append("")
    if is_compact:
        lines.append("| № | Предмет | Ауд. · Время |")
        lines.append("|:-:|:--------|:------------:|")
    else:
        lines.append("| № | Предмет | Ауд. | Время | Преподаватель |")
        lines.append("|:-:|:--------|:----:|:-----:|:--------------|")

    ordered = sorted(entries, key=lambda e: (e.position is None, e.position or 0, e.subgroup or 0))

    used = sum(len(line) + 1 for line in lines)
    for block in _pair_blocks(ordered, mode):
        if len(block) > 1:
            if is_compact:
                block_lines = [_crow(_position_label(block[0]), block[0].subject, "")]
                block_lines += [
                    _crow(
                        "",
                        f"{e.subgroup} п/г" + (f" · {e.teacher}" if e.teacher else ""),
                        _details_cell(e.audience or base_audience, e.starts_at, config),
                    )
                    for e in block
                ]
            else:
                block_lines = [
                    _row(_position_label(block[0]), block[0].subject, None, None, None, config)
                ]
                block_lines += [
                    _row("", f"{e.subgroup} п/г", e.audience or base_audience, e.starts_at, e.teacher, config)
                    for e in block
                ]
        else:
            if is_compact:
                block_lines = _compact_entry_lines(block[0], base_audience, config)
            else:
                block_lines = [_entry_row(block[0], base_audience, config)]

        used += sum(len(line) + 1 for line in block_lines)
        if used > config.rich_message_limit:
            break
        lines.extend(block_lines)

    return "\n".join(lines)


def build_broadcast_message(
    for_date: date,
    parts: list[str],
    config: AppConfig,
) -> str:
    weekday = config.weekdays_short[for_date.weekday()]
    header = f"**📅 Расписание на {for_date.strftime('%d.%m.%Y')} ({weekday})**"
    body = "\n\n---\n\n".join(parts)
    return f"{header}\n\n{body}" if body else header


def subgroup_callback(group_id: int, for_date: date, mode: str) -> str:
    return f"sg:{group_id}:{for_date.strftime('%Y%m%d')}:{mode}"


def subgroup_markup(
    group_id: int, for_date: date, mode: str = "a"
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=("🔘 " if code == mode else "⚪ ") + label,
                    callback_data=subgroup_callback(group_id, for_date, code),
                )
                for code, label in (("1", "1 п/г"), ("2", "2 п/г"), ("a", "Все"))
            ]
        ]
    )


def subgroup_markup_mode(markup: InlineKeyboardMarkup | None) -> str | None:
    if markup is None:
        return None
    for row in markup.inline_keyboard:
        for button in row:
            if button.text.startswith("🔘") and button.callback_data:
                return button.callback_data.rsplit(":", 1)[-1]
    return None


def _hrow(
    position: str, subject: str, audience: str | None,
    starts_at: time | None, teacher: str | None, config: AppConfig,
) -> str:
    pos = f"<b>{escape(position)}</b>" if position else ""
    aud = escape(audience) if audience else "—"
    t = _fmt_time(starts_at, config.time_format)
    return (
        f"<tr><td>{pos}</td><td>{escape(subject)}</td><td>{aud}</td>"
        f"<td>{escape(t)}</td><td>{escape(teacher) if teacher else '—'}</td></tr>"
    )


def _hdetails(audience: str | None, starts_at: time | None, config: AppConfig) -> str:
    parts = [
        p for p in (
            escape(audience) if audience else None,
            starts_at.strftime(config.time_format) if starts_at else None,
        )
        if p
    ]
    return " · ".join(parts) if parts else "—"


def _hcrow(position: str, subject: str, details: str) -> str:
    pos = f"<b>{escape(position)}</b>" if position else ""
    return f"<tr><td>{pos}</td><td>{escape(subject)}</td><td>{details}</td></tr>"


def _compact_hentry_rows(
    entry: TimetableEntry, base_audience: str | None, config: AppConfig
) -> list[str]:
    rows = [
        _hcrow(
            _position_label(entry), entry.subject,
            _hdetails(entry.audience or base_audience, entry.starts_at, config),
        )
    ]
    if entry.teacher:
        rows.append(f"<tr><td></td><td>{escape(entry.teacher)}</td><td></td></tr>")
    return rows


def format_group_schedule_html(
    base_audience: str | None,
    entries: list[TimetableEntry],
    config: AppConfig,
    mode: str = "a",
    is_compact: bool = False,
) -> str:
    parts: list[str] = []
    if base_audience:
        parts.append(f"<blockquote>сбор ауд. {escape(base_audience)}</blockquote>")
    if is_compact:
        parts.append("<table><tr><th>№</th><th>Предмет</th><th>Ауд. · Время</th></tr>")
    else:
        parts.append(
            "<table><tr><th>№</th><th>Предмет</th><th>Ауд.</th><th>Время</th><th>Преподаватель</th></tr>"
        )

    ordered = sorted(entries, key=lambda e: (e.position is None, e.position or 0, e.subgroup or 0))
    for block in _pair_blocks(ordered, mode):
        if len(block) > 1:
            if is_compact:
                parts.append(_hcrow(_position_label(block[0]), block[0].subject, ""))
                parts += [
                    _hcrow(
                        "",
                        f"{e.subgroup} п/г" + (f" · {e.teacher}" if e.teacher else ""),
                        _hdetails(e.audience or base_audience, e.starts_at, config),
                    )
                    for e in block
                ]
            else:
                parts.append(
                    _hrow(_position_label(block[0]), block[0].subject, None, None, None, config)
                )
                parts += [
                    _hrow("", f"{e.subgroup} п/г", e.audience or base_audience, e.starts_at, e.teacher, config)
                    for e in block
                ]
        else:
            if is_compact:
                parts.extend(_compact_hentry_rows(block[0], base_audience, config))
            else:
                entry = block[0]
                parts.append(
                    _hrow(
                        _position_label(entry), entry.subject,
                        entry.audience or base_audience, entry.starts_at, entry.teacher, config,
                    )
                )

    parts.append("</table>")
    return "".join(parts)


def build_channel_html(
    for_date: date,
    parts: list[tuple[str, str]],
    config: AppConfig,
) -> str:
    weekday = config.weekdays_short[for_date.weekday()]
    out = [f"<h3>📅 Расписание на {for_date.strftime('%d.%m.%Y')} ({weekday})</h3>"]
    for label, body in parts:
        out.append(f"<details><summary>{escape(label)}</summary>{body}</details>")
    return "".join(out)
