import html

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
    RichTextStrikethrough,
    RichTextUnion,
)

from timetabler.domain.schemas import DiffLine, PublishReport, Revision, User
from timetabler.infrastructure.config.app import AppConfig

_MAX_DIFF_GROUPS = 10
_MAX_DIFF_ROWS = 40
_OPEN_DIFF_ROWS = 12


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
    old: RichTextUnion = (
        "—" if line.old is None else RichTextStrikethrough(text=line.old)
    )
    new: RichTextUnion = (
        "—" if line.new is None else RichTextBold(text=line.new)
    )
    return [
        RichBlockTableCell(align="left", valign="middle", text=line.pos),
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


def _field(label: str, value: str) -> InputRichBlockParagraph:
    return InputRichBlockParagraph(text=[RichTextBold(text=label), f" {value}"])


def _diff_blocks(revision: Revision, is_open: bool) -> list[InputRichBlockUnion]:
    blocks: list[InputRichBlockUnion] = []
    groups = sorted(revision.diff)
    for group_id in groups[:_MAX_DIFF_GROUPS]:
        blocks.append(
            InputRichBlockDetails(
                summary=f"🎓 Группа {group_id}",
                blocks=[_diff_table(revision.diff[group_id])],
                is_open=is_open,
            )
        )
    if len(groups) > _MAX_DIFF_GROUPS:
        blocks.append(
            InputRichBlockParagraph(
                text=f"… и ещё {len(groups) - _MAX_DIFF_GROUPS} групп"
            )
        )
    return blocks


def revision_approval_blocks(
    revision: Revision, config: AppConfig
) -> list[InputRichBlockUnion]:
    kind = "новое расписание" if revision.kind == "new" else "правка"
    weekday = config.weekdays_short[revision.weekday]
    changed = ", ".join(str(g) for g in revision.changed_groups) or "—"
    blocks: list[InputRichBlockUnion] = [
        InputRichBlockSectionHeading(text=f"📝 Ревизия #{revision.id}", size=2),
        _field("📅 День:", f"{revision.for_date.strftime('%d.%m.%Y')} ({weekday})"),
        _field("🏷 Тип:", kind),
        _field("🎓 Группы:", changed),
        *_diff_blocks(revision, False),
        InputRichBlockDivider(),
        InputRichBlockParagraph(text=RichTextBold(text="Опубликовать?")),
    ]
    return blocks


def revision_report_blocks(
    report: PublishReport, config: AppConfig
) -> list[InputRichBlockUnion]:
    rev = report.revision
    is_new = rev.kind == "new"
    weekday = config.weekdays_short[rev.weekday]
    groups = (
        f"все {len(rev.changed_groups)}" if is_new
        else ", ".join(str(g) for g in rev.changed_groups) or "—"
    )
    delivered = (
        f"каналов {report.channels[0]}, чатов {report.chats[0]}, юзеров {report.users[0]}"
    )
    blocks: list[InputRichBlockUnion] = [
        InputRichBlockSectionHeading(
            text=f"📤 {'Новое расписание' if is_new else 'Расписание обновлено'} · #{rev.id}",
            size=2,
        ),
        _field("📅 День:", f"{rev.for_date.strftime('%d.%m.%Y')} ({weekday})"),
        _field("🏷 Тип:", "новое расписание" if is_new else "правка"),
        _field("🎓 Группы:", groups),
    ]
    if rev.header:
        blocks.append(_field("📝 Шапка:", shorten(rev.header, 80)))
    blocks.append(
        _field(
            "⏱ Время:",
            f"{report.age_seconds} с от обнаружения до рассылки, рассылка {report.seconds:.1f} с",
        )
    )
    blocks.append(_field("📬 Доставлено:", delivered))
    if report.failed:
        blocks.append(
            _field(
                "⚠️ Ошибок доставки:",
                f"каналов {report.channels[1]}, чатов {report.chats[1]}, юзеров {report.users[1]}",
            )
        )
    if rev.diff and not is_new:
        total_rows = sum(len(lines) for lines in rev.diff.values())
        blocks += _diff_blocks(rev, total_rows <= _OPEN_DIFF_ROWS)
    return blocks


def shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def error_text(title: str, details: str = "") -> str:
    head = f"⚠️ <b>{html.escape(shorten(title, 120))}</b>"
    if not details:
        return head
    return f"{head}\n<code>{html.escape(shorten(details, 500))}</code>"
