from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from timetabler.domain.schemas import Revision, User
from timetabler.infrastructure.config.app import AppConfig


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


def revision_approval_text(revision: Revision, config: AppConfig) -> str:
    kind = "новое расписание" if revision.kind == "new" else "правка"
    weekday = config.weekdays_short[revision.weekday]
    changed = ", ".join(str(g) for g in revision.changed_groups) or "—"
    lines = [
        f"<b>📝 Ревизия #{revision.id}</b>\n\n"
        f"<b>День:</b> {revision.for_date.strftime('%d.%m.%Y')} ({weekday})\n"
        f"<b>Тип:</b> {kind}\n"
        f"<b>Группы:</b> {changed}"
    ]
    if revision.diff:
        diff_lines = []
        for group_id in sorted(revision.diff):
            diff_lines.append(f"<b>{group_id}</b>")
            diff_lines.extend(f"  {line}" for line in revision.diff[group_id])
        shown = diff_lines[:40]
        if len(diff_lines) > 40:
            shown.append(f"  … и ещё {len(diff_lines) - 40}")
        lines.append("<blockquote>" + "\n".join(shown) + "</blockquote>")
    lines.append("<b>Опубликовать?</b>")
    return "\n\n".join(lines)
