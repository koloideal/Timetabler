from datetime import date

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InputRichMessage, Message
from aiogram_dialog import DialogManager, StartMode
from dishka import FromDishka

from timetabler.application.services.broadcast import BroadcastService
from timetabler.application.services.group_chat import GroupChatService
from timetabler.application.services.user import UserService
from timetabler.infrastructure.config.app import AppConfig
from timetabler.infrastructure.config.models import Config
from timetabler.presentation.messages import (
    group_content,
    group_setup_markup,
    subgroup_markup_mode,
)
from timetabler.presentation.telegram import TelegramNotifier
from timetabler.presentation.user_dialogs import GroupSetupSG, UserMenuSG
from timetabler.presentation.user_dialogs.group_setup import is_chat_admin


def new_user_router() -> Router:
    router = Router()

    @router.message(Command("start"), F.chat.type == "private")
    async def start(
        message: Message,
        dialog_manager: DialogManager,
        user_service: FromDishka[UserService],
        group_chat_service: FromDishka[GroupChatService],
        notifier: FromDishka[TelegramNotifier],
    ) -> None:
        assert message.from_user is not None
        user, is_new = await user_service.get_or_create(message.from_user.id, message.from_user.username)
        if is_new:
            await notifier.notify_new_user(user)
        await dialog_manager.start(UserMenuSG.main, mode=StartMode.RESET_STACK)

        for chat in await group_chat_service.get_pending_for_user(user.user_id):
            await message.answer(
                f"👋 Вы добавили меня в «{chat.title or chat.chat_id}». "
                "Настроить расписание сейчас?",
                reply_markup=group_setup_markup(chat.chat_id),
            )

    @router.message(Command("help"))
    async def help_handler(
        message: Message,
        config: FromDishka[Config],
        app_config: FromDishka[AppConfig],
    ) -> None:
        assert message.from_user is not None
        if message.from_user.id == config.bot.creator_id:
            await message.answer(app_config.creator_help)
        else:
            await message.answer(app_config.user_help)

    @router.callback_query(F.data.startswith("gchat:setup:"))
    async def on_group_setup_invite(
        call: CallbackQuery,
        dialog_manager: DialogManager,
        bot: FromDishka[Bot],
        group_chat_service: FromDishka[GroupChatService],
    ) -> None:
        chat_id = int((call.data or "").rsplit(":", 1)[-1])
        chat = await group_chat_service.get_by_id(chat_id)
        if chat is None or not await is_chat_admin(bot, chat_id, call.from_user.id):
            await call.answer("⛔ Вы не админ этого чата", show_alert=True)
            return
        state = GroupSetupSG.settings if chat.study_groups else GroupSetupSG.pick_groups
        await dialog_manager.start(state, data={"chat_id": chat_id}, mode=StartMode.RESET_STACK)
        await call.answer()

    @router.callback_query(F.data == "gchat:later")
    async def on_group_setup_later(call: CallbackQuery) -> None:
        if isinstance(call.message, Message):
            await call.message.edit_reply_markup(reply_markup=None)
        await call.answer("Хорошо — потом настроите в «Мои группы»")

    @router.callback_query(F.data.startswith("sg:"))
    async def on_subgroup_mode(
        call: CallbackQuery,
        broadcast_service: FromDishka[BroadcastService],
        app_config: FromDishka[AppConfig],
    ) -> None:
        try:
            _, gid_s, date_s, mode = (call.data or "").split(":")
            group_id = int(gid_s)
            for_date = date(int(date_s[:4]), int(date_s[4:6]), int(date_s[6:8]))
        except (ValueError, AttributeError):
            await call.answer()
            return
        if mode not in {"a", "1", "2"}:
            await call.answer()
            return

        current = subgroup_markup_mode(
            call.message.reply_markup if isinstance(call.message, Message) else None
        )
        if mode == current:
            await call.answer()
            return

        day = await broadcast_service.day_schedule(for_date)
        content = group_content(day, for_date, group_id, mode, app_config)
        if content is None or not isinstance(call.message, Message):
            await call.answer("Нет расписания за этот день", show_alert=True)
            return
        markdown, markup = content
        await call.message.edit_text(
            rich_message=InputRichMessage(markdown=markdown),
            reply_markup=markup,
        )
        await call.answer()

    return router
