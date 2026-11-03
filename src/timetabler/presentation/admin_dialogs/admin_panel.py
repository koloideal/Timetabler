import logging
from typing import Any

from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import (
    Button,
    Cancel,
    CurrentPage,
    NextPage,
    PrevPage,
    Row,
    ScrollingGroup,
    Select,
    SwitchTo,
)
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from timetabler.application.services.group_chat import GroupChatService
from timetabler.application.services.user import UserService
from timetabler.infrastructure.config.models import Config

logger = logging.getLogger(__name__)


class AdminPanelSG(StatesGroup):
    main = State()
    users_list = State()
    user_detail = State()
    admins_list = State()
    chats_list = State()
    chat_detail = State()


def _is_creator(dialog_manager: DialogManager, config: Config) -> bool:
    event_from_user = dialog_manager.middleware_data.get("event_from_user")
    return bool(event_from_user and event_from_user.id == config.bot.creator_id)


def _format_groups(groups: list[str]) -> str:
    return ", ".join(groups) if groups else "—"


@inject
async def get_admin_main_data(
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    group_chat_service: FromDishka[GroupChatService],
    config: FromDishka[Config],
    **kwargs: Any,
) -> dict[str, Any]:
    users = await user_service.list_users()
    chats = await group_chat_service.list_chats()
    return {
        "total_users": len(users),
        "total_chats": len(chats),
        "is_creator": _is_creator(dialog_manager, config),
    }


@inject
async def get_users_list_data(
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    config: FromDishka[Config],
    **kwargs: Any,
) -> dict[str, Any]:
    users = await user_service.list_users()
    users_data = []
    for user in users:
        username = f"@{user.username}" if user.username else str(user.user_id)
        badge = "👑" if user.user_id == config.bot.creator_id else "🛡" if user.is_admin else "🚫" if user.is_banned else ""
        users_data.append((f"{badge}{username}".strip(), str(user.user_id)))
    return {"users": users_data, "total_users": len(users)}


async def on_user_selected(
    call: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    manager.dialog_data["selected_user_id"] = int(item_id)
    manager.dialog_data["detail_from"] = "users"
    await manager.switch_to(AdminPanelSG.user_detail)


@inject
async def get_admins_list_data(
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    config: FromDishka[Config],
    **kwargs: Any,
) -> dict[str, Any]:
    admins = await user_service.list_admins()
    admins_data = []
    for admin in admins:
        username = f"@{admin.username}" if admin.username else str(admin.user_id)
        admins_data.append((username, str(admin.user_id)))
    return {"admins": admins_data, "total_admins": len(admins)}


async def on_admin_selected(
    call: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    manager.dialog_data["selected_user_id"] = int(item_id)
    manager.dialog_data["detail_from"] = "admins"
    await manager.switch_to(AdminPanelSG.user_detail)


@inject
async def get_user_detail_data(
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    config: FromDishka[Config],
    **kwargs: Any,
) -> dict[str, Any]:
    user_id = dialog_manager.dialog_data.get("selected_user_id")
    if not user_id:
        return {}

    user = await user_service.get_by_id(user_id)
    if not user:
        return {}

    is_creator = _is_creator(dialog_manager, config)
    is_self = user.user_id == dialog_manager.middleware_data["event_from_user"].id
    target_is_creator = user.user_id == config.bot.creator_id

    can_ban = not is_self and not target_is_creator and (is_creator or not user.is_admin)
    can_toggle_admin = is_creator and not target_is_creator

    return {
        "user_id": user.user_id,
        "username": f"@{user.username}" if user.username else "—",
        "registered_at": user.created_at.strftime("%d.%m.%Y %H:%M"),
        "groups": _format_groups(user.groups),
        "admin_status": "да 🛡" if user.is_admin else "нет",
        "ban_status": "🚫 заблокирован" if user.is_banned else "✅ активен",
        "ban_button_text": "✅ Разбанить" if user.is_banned else "🚫 Забанить",
        "admin_button_text": "🔻 Снять админа" if user.is_admin else "⭐ Сделать админом",
        "can_ban": can_ban,
        "can_toggle_admin": can_toggle_admin,
    }


@inject
async def on_ban_toggle(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    user_service: FromDishka[UserService],
    config: FromDishka[Config],
) -> None:
    user_id = manager.dialog_data.get("selected_user_id")
    target = await user_service.get_by_id(user_id) if user_id else None
    if not target:
        await call.answer("❌ Пользователь не найден", show_alert=True)
        return

    if target.user_id == config.bot.creator_id or target.user_id == call.from_user.id:
        await call.answer("❌ Нельзя забанить этого пользователя", show_alert=True)
        return

    if target.is_admin and call.from_user.id != config.bot.creator_id:
        await call.answer("❌ Банить админов может только создатель", show_alert=True)
        return

    updated = await user_service.set_banned(target.user_id, not target.is_banned)
    if updated:
        await call.answer("✅ Разбанен" if not updated.is_banned else "🚫 Забанен", show_alert=True)
    else:
        await call.answer("❌ Не удалось обновить", show_alert=True)


@inject
async def on_admin_toggle(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    user_service: FromDishka[UserService],
    config: FromDishka[Config],
) -> None:
    if call.from_user.id != config.bot.creator_id:
        await call.answer("❌ Управлять админами может только создатель", show_alert=True)
        return

    user_id = manager.dialog_data.get("selected_user_id")
    target = await user_service.get_by_id(user_id) if user_id else None
    if not target:
        await call.answer("❌ Пользователь не найден", show_alert=True)
        return

    if target.user_id == config.bot.creator_id:
        await call.answer("❌ Нельзя менять статус создателя", show_alert=True)
        return

    updated = await user_service.set_admin(target.user_id, not target.is_admin)
    if updated:
        await call.answer("⭐ Назначен админом" if updated.is_admin else "🔻 Админ снят", show_alert=True)
    else:
        await call.answer("❌ Не удалось обновить", show_alert=True)


async def on_detail_back(call: CallbackQuery, button: Button, manager: DialogManager) -> None:
    source = manager.dialog_data.get("detail_from", "users")
    target = AdminPanelSG.admins_list if source == "admins" else AdminPanelSG.users_list
    await manager.switch_to(target)


@inject
async def get_chats_list_data(
    dialog_manager: DialogManager,
    group_chat_service: FromDishka[GroupChatService],
    **kwargs: Any,
) -> dict[str, Any]:
    chats = await group_chat_service.list_chats()
    chats_data = []
    for chat in chats:
        title = chat.title or str(chat.chat_id)
        chats_data.append((title, str(chat.chat_id)))
    return {"chats": chats_data, "total_chats": len(chats)}


async def on_chat_selected(
    call: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    manager.dialog_data["selected_chat_id"] = int(item_id)
    await manager.switch_to(AdminPanelSG.chat_detail)


@inject
async def get_chat_detail_data(
    dialog_manager: DialogManager,
    group_chat_service: FromDishka[GroupChatService],
    **kwargs: Any,
) -> dict[str, Any]:
    chat_id = dialog_manager.dialog_data.get("selected_chat_id")
    if not chat_id:
        return {}

    chat = await group_chat_service.get_by_id(chat_id)
    if not chat:
        return {}

    return {
        "chat_id": chat.chat_id,
        "title": chat.title or "—",
        "groups": _format_groups(chat.groups),
        "added_at": chat.created_at.strftime("%d.%m.%Y %H:%M"),
    }


admin_panel_dialog = Dialog(
    Window(
        Format(
            "🛠 <b>Админ-панель</b>\n\n"
            "<pre>👤 {total_users} юзеров | 🏫 {total_chats} чатов</pre>\n\n"
            "Выберите раздел:"
        ),
        SwitchTo(Const("👤 Пользователи"), id="sec_users", state=AdminPanelSG.users_list),
        SwitchTo(Const("🛡 Админы"), id="sec_admins", state=AdminPanelSG.admins_list, when="is_creator"),
        SwitchTo(Const("🏫 Чаты"), id="sec_chats", state=AdminPanelSG.chats_list),
        Cancel(Const("❌ Закрыть")),
        state=AdminPanelSG.main,
        getter=get_admin_main_data,
    ),
    Window(
        Format("👤 <b>Пользователи</b> | Всего: {total_users}"),
        ScrollingGroup(
            Select(
                Format("{item[0]}"),
                id="user_select",
                item_id_getter=lambda x: x[1],
                items="users",
                on_click=on_user_selected,
            ),
            id="users_scroll",
            width=1,
            height=7,
        ),
        Row(
            PrevPage(scroll="users_scroll"),
            CurrentPage(scroll="users_scroll"),
            NextPage(scroll="users_scroll"),
        ),
        SwitchTo(Const("⬅️ Назад"), id="back_main_users", state=AdminPanelSG.main),
        state=AdminPanelSG.users_list,
        getter=get_users_list_data,
    ),
    Window(
        Format("🛡 <b>Админы</b> | Всего: {total_admins}"),
        ScrollingGroup(
            Select(
                Format("{item[0]}"),
                id="admin_select",
                item_id_getter=lambda x: x[1],
                items="admins",
                on_click=on_admin_selected,
            ),
            id="admins_scroll",
            width=1,
            height=7,
        ),
        Row(
            PrevPage(scroll="admins_scroll"),
            CurrentPage(scroll="admins_scroll"),
            NextPage(scroll="admins_scroll"),
        ),
        SwitchTo(Const("⬅️ Назад"), id="back_main_admins", state=AdminPanelSG.main),
        state=AdminPanelSG.admins_list,
        getter=get_admins_list_data,
    ),
    Window(
        Format(
            "👤 <b>Пользователь</b>\n\n"
            "<blockquote>• ID: <code>{user_id}</code>\n"
            "• Username: {username}\n"
            "• Зарегистрирован: {registered_at}\n"
            "• Группы: {groups}\n"
            "• Админ: {admin_status}\n"
            "• Статус: {ban_status}</blockquote>"
        ),
        Button(
            Format("{ban_button_text}"),
            id="ban_toggle",
            on_click=on_ban_toggle,
            when="can_ban",
        ),
        Button(
            Format("{admin_button_text}"),
            id="admin_toggle",
            on_click=on_admin_toggle,
            when="can_toggle_admin",
        ),
        Button(Const("⬅️ Назад"), id="back_to_list", on_click=on_detail_back),
        state=AdminPanelSG.user_detail,
        getter=get_user_detail_data,
    ),
    Window(
        Format("🏫 <b>Чаты</b> | Всего: {total_chats}"),
        ScrollingGroup(
            Select(
                Format("{item[0]}"),
                id="chat_select",
                item_id_getter=lambda x: x[1],
                items="chats",
                on_click=on_chat_selected,
            ),
            id="chats_scroll",
            width=1,
            height=7,
        ),
        Row(
            PrevPage(scroll="chats_scroll"),
            CurrentPage(scroll="chats_scroll"),
            NextPage(scroll="chats_scroll"),
        ),
        SwitchTo(Const("⬅️ Назад"), id="back_main_chats", state=AdminPanelSG.main),
        state=AdminPanelSG.chats_list,
        getter=get_chats_list_data,
    ),
    Window(
        Format(
            "🏫 <b>Чат</b>\n\n"
            "<blockquote>• Название: {title}\n"
            "• ID: <code>{chat_id}</code>\n"
            "• Добавлен: {added_at}\n"
            "• Группы: {groups}</blockquote>"
        ),
        SwitchTo(Const("⬅️ Назад"), id="back_to_chats", state=AdminPanelSG.chats_list),
        state=AdminPanelSG.chat_detail,
        getter=get_chat_detail_data,
    ),
)
