from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from timetabler.domain.schemas import BroadcastSummary, User
from timetabler.infrastructure.config.app import AppConfig


def broadcast_confirmation_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Разослать", callback_data="bcast:confirm"),
                InlineKeyboardButton(text="❌ Пропустить", callback_data="bcast:decline"),
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


def new_user_text(user: User) -> str:
    username = f"@{user.username}" if user.username else "—"
    return f"🆕 <b>НОВЫЙ ЮЗЕР</b>\n<pre>USERNAME  {username}\nID        {user.user_id}</pre>"


def schedule_updated_text(summary: BroadcastSummary, config: AppConfig) -> str:
    dates = ", ".join(d.strftime("%d.%m.%Y") for d in summary.dates)
    return (
        "📊 <b>РАСПИСАНИЕ ОБНОВЛЕНО</b>\n"
        f"<pre>ДЕНЬ     {config.weekdays_short[summary.weekday]} ({dates})\n"
        f"ПАР      {summary.lessons}\n"
        f"ГРУПП    {summary.groups}\n"
        f"ЮЗЕРАМ   {summary.users_sent} (+{summary.users_failed} недост.)\n"
        f"ЧАТАМ    {summary.chats_sent} (+{summary.chats_failed} недост.)</pre>"
    )
