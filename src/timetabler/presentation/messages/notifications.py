from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichBlockDivider,
    InputRichBlockParagraph,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichBlockUnion,
    RichBlockTableCell,
    RichTextBold,
    RichTextStrikethrough,
    RichTextUnion,
)

from timetabler.domain.schemas import DiffLine, Revision, User
from timetabler.infrastructure.config.app import AppConfig

_MAX_DIFF_GROUPS = 10
_MAX_DIFF_ROWS = 40


def revision_approval_markup(revision_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"rev:approve:{revision_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"rev:reject:{revision_id}"),
            ]
        ]
    )


def channel_approval_markup(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"chan:approve:{chat_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"chan:decline:{chat_id}"),
            ]
        ]
    )


def group_setup_markup(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚙️ Настроить", callback_data=f"gchat:setup:{chat_id}"),
                InlineKeyboardButton(text="⏭️ Позже", callback_data="gchat:later"),
            ]
        ]
    )


def new_user_text(user: User) -> str:
    username = f"@{user.username}" if user.username else "—"
    return (
        "<b>👤 Новый пользователь</b>\n\n"
        f"<b>Username:</b> {username}\n"
        f"<b>ID:</b> {user.user_id}"
    )


def _diff_row(line: DiffLine) -> list[RichBlockTableCell]:
    first = line.pos + (f" · {line.field}" if line.field else "")
    old: RichTextUnion = (
        "—" if line.old is None else RichTextStrikethrough(text=line.old)
    )
    new: RichTextUnion = (
        "—" if line.new is None else RichTextBold(text=line.new)
    )
    return [
        RichBlockTableCell(align="left", valign="middle", text=first),
        RichBlockTableCell(align="left", valign="middle", text=old),
        RichBlockTableCell(align="left", valign="middle", text=new),
    ]


def _diff_table(lines: list[DiffLine]) -> InputRichBlockTable:
    cells = [
        [
            RichBlockTableCell(align="left", valign="middle", text="Пара", is_header=True),
            RichBlockTableCell(align="left", valign="middle", text="Было", is_header=True),
            RichBlockTableCell(align="left", valign="middle", text="Стало", is_header=True),
        ]
    ]
    shown = lines[:_MAX_DIFF_ROWS]
    cells += [_diff_row(line) for line in shown]
    if len(lines) > _MAX_DIFF_ROWS:
        cells.append([
            RichBlockTableCell(
                align="left", valign="middle",
                text=f"… и ещё {len(lines) - _MAX_DIFF_ROWS}", colspan=3,
            )
        ])
    return InputRichBlockTable(
        cells=cells, is_bordered=True, is_striped=True, is_compact=True,
    )


def revision_approval_blocks(
    revision: Revision, config: AppConfig
) -> list[InputRichBlockUnion]:
    kind = "новое расписание" if revision.kind == "new" else "правка"
    weekday = config.weekdays_short[revision.weekday]
    changed = ", ".join(str(g) for g in revision.changed_groups) or "—"

    def field(label: str, value: str) -> InputRichBlockParagraph:
        return InputRichBlockParagraph(text=[RichTextBold(text=label), f" {value}"])

    blocks: list[InputRichBlockUnion] = [
        InputRichBlockSectionHeading(text=f"📝 Ревизия #{revision.id}", size=2),
        field("День:", f"{revision.for_date.strftime('%d.%m.%Y')} ({weekday})"),
        field("Тип:", kind),
        field("Группы:", changed),
    ]
    if revision.diff:
        groups = sorted(revision.diff)
        for group_id in groups[:_MAX_DIFF_GROUPS]:
            blocks.append(InputRichBlockDivider())
            blocks.append(
                InputRichBlockSectionHeading(text=f"🎓 Группа {group_id}", size=3)
            )
            blocks.append(_diff_table(revision.diff[group_id]))
        if len(groups) > _MAX_DIFF_GROUPS:
            blocks.append(InputRichBlockDivider())
            blocks.append(
                InputRichBlockParagraph(
                    text=f"… и ещё {len(groups) - _MAX_DIFF_GROUPS} групп"
                )
            )
    blocks.append(InputRichBlockDivider())
    blocks.append(InputRichBlockParagraph(text=RichTextBold(text="Опубликовать?")))
    return blocks
