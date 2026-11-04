from aiogram import F, Router
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import DialogManager, StartMode
from dishka import FromDishka

from timetabler.application.services.broadcast import BroadcastService
from timetabler.application.services.channel import ChannelService
from timetabler.application.services.revision import RevisionService
from timetabler.presentation.admin_dialogs.admin_panel import AdminPanelSG


def new_admin_router() -> Router:
    router = Router()

    @router.message(Command("admin"))
    async def admin_panel_entry(message: Message, dialog_manager: DialogManager) -> None:
        await dialog_manager.start(AdminPanelSG.main, mode=StartMode.RESET_STACK)

    @router.callback_query(F.data.startswith("rev:approve:"))
    async def on_revision_approve(
        call: CallbackQuery,
        revision_service: FromDishka[RevisionService],
        broadcast_service: FromDishka[BroadcastService],
    ) -> None:
        revision_id = int((call.data or "").rsplit(":", 1)[-1])
        revision = await revision_service.get_by_id(revision_id)
        if revision is None or revision.status != "pending_approval":
            await call.answer("Уже обработано", show_alert=True)
            return

        await revision_service.set_status(revision.id, "approved")
        await broadcast_service.publish_revision(revision)

        if isinstance(call.message, Message):
            await call.message.edit_reply_markup(reply_markup=None)
        await call.answer("✅ Опубликовано", show_alert=True)

    @router.callback_query(F.data.startswith("rev:reject:"))
    async def on_revision_reject(
        call: CallbackQuery,
        revision_service: FromDishka[RevisionService],
    ) -> None:
        revision_id = int((call.data or "").rsplit(":", 1)[-1])
        revision = await revision_service.get_by_id(revision_id)
        if revision is None or revision.status != "pending_approval":
            await call.answer("Уже обработано", show_alert=True)
            return

        await revision_service.set_status(revision.id, "rejected")

        if isinstance(call.message, Message):
            await call.message.edit_reply_markup(reply_markup=None)
        await call.answer("❌ Ревизия отклонена", show_alert=True)

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
