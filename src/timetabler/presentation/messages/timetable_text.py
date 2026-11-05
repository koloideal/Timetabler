from datetime import date, time

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichBlockDetails,
    InputRichBlockDivider,
    InputRichBlockParagraph,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichBlockUnion,
    RichBlockTableCell,
    RichTextBold,
    RichTextItalic,
    RichTextUnion,
)

from timetabler.domain.schemas import TimetableEntry
from timetabler.infrastructure.config.app import AppConfig


def _fmt_time(starts_at: time | None, time_format: str) -> str:
    return f"⏰ с {starts_at.strftime(time_format)}" if starts_at else "—"


def _details_text(audience: str | None, starts_at: time | None, config: AppConfig) -> str:
    parts = [
        p for p in (
            audience,
            starts_at.strftime(config.time_format) if starts_at else None,
        )
        if p
    ]
    return " · ".join(parts) if parts else "—"


def _position_label(entry: TimetableEntry) -> str:
    return "–" if entry.position is None else str(entry.position)


def _cell(
    text: RichTextUnion | None,
    align: str = "center",
    *,
    header: bool = False,
) -> RichBlockTableCell:
    return RichBlockTableCell(
        align=align,
        valign="middle",
        text=text,
        is_header=True if header else None,
    )


def _header_cells(is_compact: bool) -> list[RichBlockTableCell]:
    labels = (
        ["№", "Предмет", "Ауд. · Время"]
        if is_compact
        else ["№", "Предмет", "Ауд.", "Время", "Преподаватель"]
    )
    aligns = ["center", "left", "center", "center", "left"]
    return [_cell(label, align=align, header=True) for label, align in zip(labels, aligns)]


def _full_entry_row(
    entry: TimetableEntry, base_audience: str | None, config: AppConfig
) -> list[RichBlockTableCell]:
    return [
        _cell(RichTextBold(text=_position_label(entry))),
        _cell(RichTextBold(text=entry.subject), align="left"),
        _cell(entry.audience or base_audience or "—"),
        _cell(_fmt_time(entry.starts_at, config.time_format)),
        _cell(entry.teacher or "—", align="left"),
    ]


def _compact_entry_rows(
    entry: TimetableEntry, base_audience: str | None, config: AppConfig
) -> list[list[RichBlockTableCell]]:
    subject: RichTextUnion = RichTextBold(text=entry.subject)
    if entry.teacher:
        subject = [RichTextBold(text=entry.subject), f". {entry.teacher}"]
    return [
        [
            _cell(RichTextBold(text=_position_label(entry))),
            _cell(subject, align="left"),
            _cell(_details_text(entry.audience or base_audience, entry.starts_at, config)),
        ]
    ]


def _full_block_rows(
    block: list[TimetableEntry], base_audience: str | None, config: AppConfig
) -> list[list[RichBlockTableCell]]:
    rows = [
        [
            _cell(RichTextBold(text=_position_label(block[0]))),
            _cell(RichTextBold(text=block[0].subject), align="left"),
            _cell("—"),
            _cell("—"),
            _cell("—", align="left"),
        ]
    ]
    rows += [
        [
            _cell(""),
            _cell(f"{e.subgroup} п/г", align="left"),
            _cell(e.audience or base_audience or "—"),
            _cell(_fmt_time(e.starts_at, config.time_format)),
            _cell(e.teacher or "—", align="left"),
        ]
        for e in block
    ]
    return rows


def _compact_block_rows(
    block: list[TimetableEntry], base_audience: str | None, config: AppConfig
) -> list[list[RichBlockTableCell]]:
    rows = [
        [
            _cell(RichTextBold(text=_position_label(block[0]))),
            _cell(RichTextBold(text=block[0].subject), align="left"),
            _cell(""),
        ]
    ]
    rows += [
        [
            _cell(""),
            _cell(
                f"{e.subgroup} п/г" + (f" · {e.teacher}" if e.teacher else ""),
                align="left",
            ),
            _cell(_details_text(e.audience or base_audience, e.starts_at, config)),
        ]
        for e in block
    ]
    return rows


def _text_len(text: RichTextUnion | None) -> int:
    if isinstance(text, str):
        return len(text)
    if isinstance(text, list):
        return sum(_text_len(item) for item in text)
    if isinstance(text, RichTextBold) and isinstance(text.text, str):
        return len(text.text)
    return 0


def _row_text_len(row: list[RichBlockTableCell]) -> int:
    return sum(_text_len(cell.text) for cell in row)


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


def schedule_table(
    entries: list[TimetableEntry],
    base_audience: str | None,
    config: AppConfig,
    mode: str = "a",
    is_compact: bool = False,
) -> InputRichBlockTable:
    cells = [_header_cells(is_compact)]
    ordered = sorted(entries, key=lambda e: (e.position is None, e.position or 0, e.subgroup or 0))

    used = _row_text_len(cells[0])
    for block in _pair_blocks(ordered, mode):
        if is_compact:
            block_rows = (
                _compact_block_rows(block, base_audience, config)
                if len(block) > 1
                else _compact_entry_rows(block[0], base_audience, config)
            )
        else:
            block_rows = (
                _full_block_rows(block, base_audience, config)
                if len(block) > 1
                else [_full_entry_row(block[0], base_audience, config)]
            )

        used += sum(_row_text_len(row) for row in block_rows)
        if used > config.rich_message_limit:
            break
        cells.extend(block_rows)

    return InputRichBlockTable(
        cells=cells,
        is_bordered=True,
        is_striped=True,
        is_compact=True,
    )


def format_group_schedule_body(
    base_audience: str | None,
    entries: list[TimetableEntry],
    config: AppConfig,
    mode: str = "a",
    is_compact: bool = False,
) -> list[InputRichBlockUnion]:
    return [schedule_table(entries, base_audience, config, mode, is_compact)]


def format_group_schedule(
    group_label: str,
    base_audience: str | None,
    entries: list[TimetableEntry],
    config: AppConfig,
    mode: str = "a",
    is_compact: bool = False,
) -> list[InputRichBlockUnion]:
    return [
        InputRichBlockSectionHeading(text=f"🎓 Группа {group_label}", size=3),
        *format_group_schedule_body(base_audience, entries, config, mode, is_compact),
    ]


def build_broadcast_blocks(
    for_date: date,
    parts: list[list[InputRichBlockUnion]],
    config: AppConfig,
) -> list[InputRichBlockUnion]:
    weekday = config.weekdays_short[for_date.weekday()]
    blocks: list[InputRichBlockUnion] = [
        InputRichBlockSectionHeading(
            text=f"📅 Расписание на {for_date.strftime('%d.%m.%Y')} ({weekday})",
            size=2,
        ),
    ]
    for part in parts:
        if not part:
            continue
        blocks.append(InputRichBlockDivider())
        blocks.extend(part)
    return blocks


def build_channel_blocks(
    for_date: date,
    parts: list[tuple[str, list[InputRichBlockUnion]]],
    config: AppConfig,
) -> list[InputRichBlockUnion]:
    weekday = config.weekdays_short[for_date.weekday()]
    blocks: list[InputRichBlockUnion] = [
        InputRichBlockSectionHeading(
            text=f"📅 Расписание на {for_date.strftime('%d.%m.%Y')} ({weekday})",
            size=2,
        ),
    ]
    blocks += [
        InputRichBlockDetails(summary=label, blocks=body, is_open=False)
        for label, body in parts
    ]
    return blocks


def note_blocks(note: str) -> list[InputRichBlockUnion]:
    return [
        InputRichBlockDivider(),
        InputRichBlockParagraph(text=[RichTextItalic(text=f"🔄 {note}")]),
    ]


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
