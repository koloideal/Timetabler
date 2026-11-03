from aiogram import F, Router
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import DialogManager, StartMode
from dishka import FromDishka

from timetabler.application.services.broadcast import BroadcastService
from timetabler.application.services.channel import ChannelService
from timetabler.application.services.settings import SettingsService
from timetabler.application.services.sheets import SheetsService
from timetabler.presentation.admin_dialogs.admin_panel import AdminPanelSG


def new_admin_router() -> Router:
    router = Router()

    @router.message(Command("admin"))
    async def admin_panel_entry(message: Message, dialog_manager: DialogManager) -> None:
        await dialog_manager.start(AdminPanelSG.main, mode=StartMode.RESET_STACK)

    @router.callback_query(F.data == "bcast:confirm")
    async def on_broadcast_confirm(
        call: CallbackQuery,
        broadcast_service: FromDishka[BroadcastService],
        sheets_service: FromDishka[SheetsService],
        settings_service: FromDishka[SettingsService],
    ) -> None:
        pending = await settings_service.get_pending_broadcast()
        if pending is None:
            await call.answer("Нечего подтверждать", show_alert=True)
            return

        sent = failed = chats = chats_failed = 0
        for for_date in pending.dates:
            report = await broadcast_service.broadcast(for_date)
            sent += report.users_sent
            failed += report.users_failed
            chats += report.chats_sent
            chats_failed += report.chats_failed

        await sheets_service.mark_header(pending.weekday, pending.marker)
        await settings_service.set_pending_broadcast(None)

        if isinstance(call.message, Message):
            await call.message.edit_reply_markup(reply_markup=None)
        await call.answer(
            f"✅ Разослано: {sent} юзерам (+{failed} недост.), {chats} чатам",
            show_alert=True,
        )

    @router.callback_query(F.data == "bcast:decline")
    async def on_broadcast_decline(
        call: CallbackQuery,
        sheets_service: FromDishka[SheetsService],
        settings_service: FromDishka[SettingsService],
    ) -> None:
        pending = await settings_service.get_pending_broadcast()
        if pending is not None:
            await sheets_service.mark_header(pending.weekday, pending.marker)
            await settings_service.set_pending_broadcast(None)

        if isinstance(call.message, Message):
            await call.message.edit_reply_markup(reply_markup=None)
        await call.answer("❌ Рассылка пропущена", show_alert=True)

    @router.callback_query(F.data.startswith("chan:approve:"))
    async def on_channel_approve(
        call: CallbackQuery,
        channel_service: FromDishka[ChannelService],
    ) -> None:
        chat_id = int((call.data or "").rsplit(":", 1)[-1])
        channel = await channel_service.approve(chat_id)
        if call.bot is not None:
            try:
                await call.bot.send_message(
                chat_id, "✅ Бот подключён — сюда будет приходить расписание."
                )
            except TelegramAPIError:
                pass
        if isinstance(call.message, Message):
            await call.message.edit_reply_markup(reply_markup=None)
        title = channel.title if channel else chat_id
        await call.answer(f"✅ «{title}» в рассылке", show_alert=True)

    @router.callback_query(F.data.startswith("chan:decline:"))
    async def on_channel_decline(
        call: CallbackQuery,
        channel_service: FromDishka[ChannelService],
    ) -> None:
        chat_id = int((call.data or "").rsplit(":", 1)[-1])
        if call.bot is not None:
            try:
                await call.bot.leave_chat(chat_id)
            except TelegramAPIError:
                pass
        await channel_service.remove(chat_id)
        if isinstance(call.message, Message):
            await call.message.edit_reply_markup(reply_markup=None)
        await call.answer("❌ Канал отклонён, я вышел", show_alert=True)

    return router
