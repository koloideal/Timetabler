from datetime import date

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

from timetabler.application.services.lesson_timing import format_range
from timetabler.domain.schemas import ResolvedLesson
from timetabler.infrastructure.config.app import AppConfig


def _details_text(lesson: ResolvedLesson, base_audience: str | None) -> str:
    parts = [
        p
        for p in (
            lesson.audience or base_audience,
            format_range(lesson.start, lesson.end) if lesson.start is not None else None,
        )
        if p
    ]
    return " · ".join(parts) if parts else "—"


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


def _subject_text(lesson: ResolvedLesson) -> RichTextUnion:
    if lesson.teacher:
        return [RichTextBold(text=lesson.subject), f". {lesson.teacher}"]
    return RichTextBold(text=lesson.subject)


def _lesson_row(
    lesson: ResolvedLesson,
    label: str,
    base_audience: str | None,
    is_compact: bool,
    role: str = "normal",
) -> list[RichBlockTableCell]:
    if role == "variant" and lesson.subgroup is not None:
        subject: RichTextUnion = (
            f"{lesson.subgroup} п/г" + (f" · {lesson.teacher}" if lesson.teacher else "")
            if is_compact
            else f"{lesson.subgroup} п/г"
        )
    elif role == "header":
        subject = RichTextBold(text=lesson.subject)
    else:
        subject = _subject_text(lesson)
    if is_compact:
        details = _details_text(lesson, base_audience) if role != "header" else ""
        return [
            _cell(RichTextBold(text=label) if label else ""),
            _cell(subject, align="left"),
            _cell(details),
        ]
    if role == "header":
        return [
            _cell(RichTextBold(text=label) if label else ""),
            _cell(subject, align="left"),
            _cell("—"),
            _cell("—"),
            _cell("—", align="left"),
        ]
    return [
        _cell(RichTextBold(text=label) if label else ""),
        _cell(subject, align="left"),
        _cell(lesson.audience or base_audience or "—"),
        _cell(format_range(lesson.start, lesson.end)),
        _cell(lesson.teacher or "—", align="left"),
    ]


def _display_rows(
    lessons: list[ResolvedLesson], mode: str
) -> list[tuple[str, ResolvedLesson, str]]:
    if mode != "a":
        sub = int(mode)
        return [
            (str(l.ordinal), l, "normal")
            for l in sorted(
                (l for l in lessons if l.subgroup in (sub, None)),
                key=lambda l: l.ordinal,
            )
        ]
    ordered = sorted(
        lessons, key=lambda l: (l.position is None, l.position or 0, l.subgroup or 0)
    )
    blocks: list[list[ResolvedLesson]] = []
    for l in ordered:
        if (
            blocks
            and blocks[-1][0].position == l.position
            and blocks[-1][0].subject == l.subject
        ):
            blocks[-1].append(l)
        else:
            blocks.append([l])
    rows: list[tuple[str, ResolvedLesson, str]] = []
    for block in blocks:
        variants: list[ResolvedLesson] = []
        seen: set[tuple] = set()
        for l in block:
            key = (l.start, l.end, l.teacher, l.audience)
            if key not in seen:
                seen.add(key)
                variants.append(l)
        pos = "–" if block[0].position is None else str(block[0].position)
        if len(variants) == 1:
            rows.append((pos, variants[0], "normal"))
        else:
            rows.append((pos, block[0], "header"))
            rows += [("", l, "variant") for l in variants]
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


def schedule_table(
    lessons: list[ResolvedLesson],
    base_audience: str | None,
    config: AppConfig,
    mode: str = "a",
    is_compact: bool = False,
) -> InputRichBlockTable:
    cells = [_header_cells(is_compact)]

    used = _row_text_len(cells[0])
    for label, lesson, role in _display_rows(lessons, mode):
        row = _lesson_row(lesson, label, base_audience, is_compact, role)
        used += _row_text_len(row)
        if used > config.rich_message_limit:
            break
        cells.append(row)

    return InputRichBlockTable(
        cells=cells,
        is_bordered=True,
        is_striped=True,
        is_compact=True,
    )


def format_group_schedule_body(
    base_audience: str | None,
    lessons: list[ResolvedLesson],
    config: AppConfig,
    mode: str = "a",
    is_compact: bool = False,
) -> list[InputRichBlockUnion]:
    return [schedule_table(lessons, base_audience, config, mode, is_compact)]


def format_group_schedule(
    group_label: str,
    base_audience: str | None,
    lessons: list[ResolvedLesson],
    config: AppConfig,
    mode: str = "a",
    is_compact: bool = False,
) -> list[InputRichBlockUnion]:
    return [
        InputRichBlockSectionHeading(text=f"🎓 Группа {group_label}", size=3),
        *format_group_schedule_body(base_audience, lessons, config, mode, is_compact),
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
