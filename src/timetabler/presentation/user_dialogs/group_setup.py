import logging
from datetime import date
from typing import cast

from aiogram import Bot, F
from aiogram.enums import ChatMemberStatus
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, User
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import (
    Button,
    Column,
    ManagedMultiselect,
    Multiselect,
    Row,
    ScrollingGroup,
    Select,
    SwitchTo,
)
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from timetabler.application.services.broadcast import BroadcastService
from timetabler.application.services.group_chat import GroupChatService
from timetabler.application.services.poller import next_study_day
from timetabler.application.services.revision import RevisionService
from timetabler.application.services.study_group import StudyGroupService
from timetabler.domain.schemas import GroupChat


class GroupSetupSG(StatesGroup):
    chats_list = State()
    pick_groups = State()
    settings = State()
    pin_denied = State()


async def is_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)


async def manageable_chats(
    bot: Bot, group_chat_service: GroupChatService, user_id: int
) -> list[GroupChat]:
    manageable = []
    for chat in await group_chat_service.list_chats():
        try:
            me = await bot.get_chat_member(chat.chat_id, bot.id)
        except Exception:
            continue
        if me.status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
            continue
        if await is_chat_admin(bot, chat.chat_id, user_id):
            manageable.append(chat)
    return manageable


def _chat_label(chat: GroupChat) -> str:
    title = chat.title or str(chat.chat_id)
    if not chat.study_groups:
        return f"{title} · ⚠️ не настроена"
    groups = ", ".join(str(g) for g in chat.study_groups)
    return f"{title} · {groups}"


async def _current_chat(
    dialog_manager: DialogManager, group_chat_service: GroupChatService
) -> GroupChat | None:
    chat_id = dialog_manager.dialog_data.get("chat_id")
    if chat_id is None:
        return None
    return await group_chat_service.get_by_id(int(chat_id))


@inject
async def get_chats_list_data(
    dialog_manager: DialogManager,
    group_chat_service: FromDishka[GroupChatService],
    **kwargs: object,
) -> dict[str, object]:
    user = dialog_manager.middleware_data.get("event_from_user")
    bot = dialog_manager.middleware_data.get("bot")
    if not isinstance(user, User) or not isinstance(bot, Bot):
        return {"chats": [], "has_chats": False}

    chats = await manageable_chats(bot, group_chat_service, user.id)
    if len(chats) == 1:
        dialog_manager.dialog_data["chat_id"] = chats[0].chat_id
        await dialog_manager.switch_to(
            GroupSetupSG.settings if chats[0].study_groups else GroupSetupSG.pick_groups
        )
        return {"chats": [], "has_chats": True}
    return {
        "chats": [(str(c.chat_id), _chat_label(c)) for c in chats],
        "has_chats": bool(chats),
    }


@inject
async def get_pick_groups_data(
    dialog_manager: DialogManager,
    group_chat_service: FromDishka[GroupChatService],
    revision_service: FromDishka[RevisionService],
    study_group_service: FromDishka[StudyGroupService],
    **kwargs: object,
) -> dict[str, object]:
    chat = await _current_chat(dialog_manager, group_chat_service)
    group_ids = await revision_service.latest_group_ids()
    aliases = {g.group_id: g.alias for g in await study_group_service.list_groups()}
    items = [
        (g, f"{g} — {aliases[g]}" if aliases.get(g) else str(g)) for g in group_ids
    ]
    if chat is not None:
        widget = cast(
            ManagedMultiselect[int], dialog_manager.find("chat_groups_ms")
        )
        widget.widget.set_widget_data(
            dialog_manager, [g for g in chat.study_groups if g in group_ids]
        )
    return {"groups": items, "has_groups": bool(items)}


@inject
async def get_settings_data(
    dialog_manager: DialogManager,
    group_chat_service: FromDishka[GroupChatService],
    **kwargs: object,
) -> dict[str, object]:
    labels = {"not_configured": "⚠️ Не настроена", "active": "🟢 Включена", "disabled": "🔴 Выключена"}
    chat = await _current_chat(dialog_manager, group_chat_service)
    if chat is None:
        return {
            "title": "—", "groups": "—", "status": "—", "pin": "—",
            "pin_toggle": "—", "active_toggle": "—", "configured": False,
        }
    return {
        "title": chat.title or str(chat.chat_id),
        "groups": ", ".join(str(g) for g in chat.study_groups) or "—",
        "status": labels.get(chat.status, chat.status),
        "pin": "🟢 вкл" if chat.pin_enabled else "🔴 выкл",
        "pin_toggle": "📌 Выключить закреп" if chat.pin_enabled else "📌 Включить закреп",
        "active_toggle": "🔴 Отключить рассылку" if chat.status == "active" else "🟢 Включить рассылку",
        "configured": bool(chat.study_groups),
    }


@inject
async def get_pin_denied_data(
    dialog_manager: DialogManager,
    group_chat_service: FromDishka[GroupChatService],
    **kwargs: object,
) -> dict[str, object]:
    chat = await _current_chat(dialog_manager, group_chat_service)
    return {"title": (chat.title or str(chat.chat_id)) if chat else "—"}


@inject
async def on_chat_selected(
    callback: CallbackQuery,
    widget: Select,
    dialog_manager: DialogManager,
    item_id: str,
    group_chat_service: FromDishka[GroupChatService],
) -> None:
    chat = await group_chat_service.get_by_id(int(item_id))
    if chat is None:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return
    bot = callback.bot
    if bot is None or callback.from_user is None or not await is_chat_admin(
        bot, chat.chat_id, callback.from_user.id
    ):
        await callback.answer("❌ Нужны права администратора чата", show_alert=True)
        return
    dialog_manager.dialog_data["chat_id"] = chat.chat_id
    await dialog_manager.switch_to(
        GroupSetupSG.settings if chat.study_groups else GroupSetupSG.pick_groups
    )


@inject
async def on_groups_save(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    group_chat_service: FromDishka[GroupChatService],
    broadcast_service: FromDishka[BroadcastService],
) -> None:
    chat = await _current_chat(dialog_manager, group_chat_service)
    bot = callback.bot
    if chat is None or bot is None or callback.from_user is None:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return
    if not await is_chat_admin(bot, chat.chat_id, callback.from_user.id):
        await callback.answer("❌ Нужны права администратора чата", show_alert=True)
        return

    ms = cast(ManagedMultiselect[int], dialog_manager.find("chat_groups_ms"))
    group_ids = sorted(int(g) for g in ms.get_checked())
    if not group_ids:
        await callback.answer("❌ Выберите хотя бы одну группу", show_alert=True)
        return

    was_configured = bool(chat.study_groups)
    updated = await group_chat_service.select_groups(
        chat.chat_id, group_ids, callback.from_user.id
    )
    if updated is None:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return

    if not was_configured:
        groups_text = ", ".join(str(g) for g in group_ids)
        try:
            await bot.send_message(chat.chat_id, f"✅ Расписание подключено: {groups_text}")
        except Exception:
            logging.getLogger(__name__).warning(
                "Cannot notify chat %s about setup", chat.chat_id
            )
        await broadcast_service.deliver_to_chat(updated, next_study_day(date.today()))

    await callback.answer("✅ Группы сохранены")
    await dialog_manager.switch_to(GroupSetupSG.settings)


@inject
async def on_toggle_pin(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    group_chat_service: FromDishka[GroupChatService],
) -> None:
    chat = await _current_chat(dialog_manager, group_chat_service)
    bot = callback.bot
    if chat is None or bot is None or callback.from_user is None:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return
    if not await is_chat_admin(bot, chat.chat_id, callback.from_user.id):
        await callback.answer("❌ Нужны права администратора чата", show_alert=True)
        return

    if chat.pin_enabled:
        for mid in chat.pinned_message_ids:
            try:
                await bot.unpin_chat_message(chat.chat_id, message_id=mid)
            except Exception:
                pass
        await group_chat_service.set_pinned_messages(chat.chat_id, [])
        await group_chat_service.set_pin(chat.chat_id, False)
        return

    can_pin = False
    try:
        me = await bot.get_chat_member(chat.chat_id, bot.id)
        can_pin = me.status == ChatMemberStatus.CREATOR or (
            me.status == ChatMemberStatus.ADMINISTRATOR
            and getattr(me, "can_pin_messages", False)
        )
    except Exception:
        pass
    if not can_pin:
        await dialog_manager.switch_to(GroupSetupSG.pin_denied)
        return
    await group_chat_service.set_pin(chat.chat_id, True)


@inject
async def on_send_test(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    group_chat_service: FromDishka[GroupChatService],
    broadcast_service: FromDishka[BroadcastService],
) -> None:
    chat = await _current_chat(dialog_manager, group_chat_service)
    bot = callback.bot
    if chat is None or bot is None or callback.from_user is None:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return
    if not await is_chat_admin(bot, chat.chat_id, callback.from_user.id):
        await callback.answer("❌ Нужны права администратора чата", show_alert=True)
        return
    result = await broadcast_service.deliver_to_chat(chat, next_study_day(date.today()))
    text = {
        "sent": "✅ Отправлено",
        "empty": "❌ Нет расписания для выбранных групп",
        "failed": "❌ Не удалось отправить",
    }.get(result, result)
    await callback.answer(text, show_alert=True)


@inject
async def on_toggle_active(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    group_chat_service: FromDishka[GroupChatService],
) -> None:
    chat = await _current_chat(dialog_manager, group_chat_service)
    bot = callback.bot
    if chat is None or bot is None or callback.from_user is None:
        await callback.answer("❌ Чат не найден", show_alert=True)
        return
    if not await is_chat_admin(bot, chat.chat_id, callback.from_user.id):
        await callback.answer("❌ Нужны права администратора чата", show_alert=True)
        return
    enabled = chat.status != "active"
    await group_chat_service.set_enabled(chat.chat_id, enabled)
    await callback.answer(
        "🟢 Рассылка включена" if enabled else "🔴 Рассылка выключена"
    )


def build_group_setup_dialog() -> Dialog:
    from timetabler.presentation.user_dialogs.menu import UserMenuSG

    return Dialog(
        Window(
            Const(
                "<b>💬 Мои чаты</b>\n\n"
                "Нет чатов. Добавьте меня в группу и нажмите «💬 Мои чаты» снова.",
                when=~F["has_chats"],
            ),
            Const(
                "<b>💬 Мои чаты</b>\n\n"
                "Выберите чат для настройки:",
                when=F["has_chats"],
            ),
            Column(
                Select(
                    Format("{item[1]}"),
                    id="chat_sel",
                    item_id_getter=lambda item: item[0],
                    items="chats",
                    on_click=on_chat_selected,
                ),
                when=F["has_chats"],
            ),
            SwitchTo(Const("◀️ В главное меню"), id="to_menu", state=UserMenuSG.main),
            state=GroupSetupSG.chats_list,
            getter=get_chats_list_data,
        ),
        Window(
            Const(
                "<b>🎓 Группы расписания</b>\n\n"
                "Выберите группы для этого чата:",
                when=F["has_groups"],
            ),
            Const(
                "<b>🎓 Группы расписания</b>\n\n"
                "Расписание ещё не загружено — групп нет. Попробуйте позже.",
                when=~F["has_groups"],
            ),
            ScrollingGroup(
                Multiselect(
                    Format("✅ {item[1]}"),
                    Format("⬜ {item[1]}"),
                    id="chat_groups_ms",
                    item_id_getter=lambda item: item[0],
                    items="groups",
                ),
                id="chat_groups_scroll",
                width=2,
                height=7,
                when=F["has_groups"],
            ),
            Row(
                Button(Const("✅ Сохранить"), id="save_groups", on_click=on_groups_save, when=F["has_groups"]),
                SwitchTo(Const("❌ Отмена"), id="back_settings", state=GroupSetupSG.settings),
            ),
            state=GroupSetupSG.pick_groups,
            getter=get_pick_groups_data,
        ),
        Window(
            Format(
                "<b>💬 {title}</b>\n\n"
                "<b>Группы:</b> {groups}\n"
                "<b>Рассылка:</b> {status}\n"
                "<b>Закреп:</b> {pin}"
            ),
            Column(
                SwitchTo(Const("✏️ Изменить группы"), id="change_groups", state=GroupSetupSG.pick_groups, when=F["configured"]),
                Button(Format("{pin_toggle}"), id="pin_toggle", on_click=on_toggle_pin, when=F["configured"]),
                Button(Const("📤 Тестовая отправка"), id="send_test", on_click=on_send_test, when=F["configured"]),
                Button(Format("{active_toggle}"), id="active_toggle", on_click=on_toggle_active, when=F["configured"]),
            ),
            SwitchTo(Const("◀️ Назад"), id="back_chats", state=GroupSetupSG.chats_list),
            state=GroupSetupSG.settings,
            getter=get_settings_data,
        ),
        Window(
            Format(
                "<b>📌 Закреп недоступен</b>\n\n"
                "Выдайте мне права администратора с правом «Закрепление сообщений» "
                "в «{title}» и проверьте снова."
            ),
            Row(
                Button(Const("🔄 Проверить снова"), id="pin_check", on_click=on_toggle_pin),
                SwitchTo(Const("◀️ Назад"), id="back_settings2", state=GroupSetupSG.settings),
            ),
            state=GroupSetupSG.pin_denied,
            getter=get_pin_denied_data,
        ),
    )
