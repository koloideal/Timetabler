from datetime import date, time

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from timetabler.domain.schemas import TimetableEntry
from timetabler.infrastructure.config.app import AppConfig

_MD_SPECIALS = ("\\", "|", "*", "_", "~", "[", "]", "(", ")")

SUBGROUP_MODES = (("1", "Только 1 п/г"), ("2", "Только 2 п/г"), ("a", "Все"))


def _md(text: str) -> str:
    for char in _MD_SPECIALS:
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
) -> str:
    lines = [f"### 📚 ГРУППА {_md(group_label)}"]
    if base_audience:
        lines.append(f"> сбор ауд. {_md(base_audience)}")

    lines.append("")
    lines.append("| № | Предмет | Ауд. | Время | Преподаватель |")
    lines.append("|:-:|:--------|:----:|:-----:|:--------------|")

    ordered = sorted(entries, key=lambda e: (e.position is None, e.position or 0, e.subgroup or 0))

    used = sum(len(line) + 1 for line in lines)
    for block in _pair_blocks(ordered, mode):
        if len(block) > 1:
            block_lines = [
                _row(_position_label(block[0]), block[0].subject, None, None, None, config)
            ]
            block_lines += [
                _row("", f"{e.subgroup} п/г", e.audience or base_audience, e.starts_at, e.teacher, config)
                for e in block
            ]
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
    header = f"**📅 РАСПИСАНИЕ НА {for_date.strftime('%d.%m.%Y')} ({weekday})**"
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
                    text=("✅ " if code == mode else "") + label,
                    callback_data=subgroup_callback(group_id, for_date, code),
                )
                for code, label in SUBGROUP_MODES
            ]
        ]
    )


def subgroup_markup_mode(markup: InlineKeyboardMarkup | None) -> str | None:
    if markup is None:
        return None
    for row in markup.inline_keyboard:
        for button in row:
            if button.text.startswith("✅") and button.callback_data:
                return button.callback_data.rsplit(":", 1)[-1]
    return None
