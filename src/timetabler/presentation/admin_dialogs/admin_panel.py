import logging
from typing import Any

from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import (
    Button,
    Row,
    ScrollingGroup,
    Select,
    SwitchTo,
)
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from timetabler.application.services.bot import BotService
from timetabler.application.services.group_chat import GroupChatService
from timetabler.application.services.study_group import StudyGroupService
from timetabler.application.services.user import UserService
from timetabler.infrastructure.config.models import Config

logger = logging.getLogger(__name__)


class AdminPanelSG(StatesGroup):
    main = State()
    users_list = State()
    user_detail = State()
    admins_list = State()
    add_admin_pick = State()
    add_admin_confirm = State()
    chats_list = State()
    chat_detail = State()
    groups_list = State()
    group_detail = State()
    group_del_confirm = State()
    group_add_id = State()
    group_add_alias = State()


def _is_creator(dialog_manager: DialogManager, config: Config) -> bool:
    event_from_user = dialog_manager.middleware_data.get("event_from_user")
    return bool(event_from_user and event_from_user.id == config.bot.creator_id)


def _format_groups(groups: list[str]) -> str:
    return ", ".join(groups) if groups else "—"


def _user_label(user_id: int, username: str | None) -> str:
    return f"@{username}" if username else str(user_id)


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
        badge = "👑" if user.user_id == config.bot.creator_id else "🛡" if user.is_admin else "🚫" if user.is_banned else ""
        users_data.append((f"{badge}{_user_label(user.user_id, user.username)}".strip(), str(user.user_id)))
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
    **kwargs: Any,
) -> dict[str, Any]:
    admins = await user_service.list_admins()
    admins_data = [(_user_label(a.user_id, a.username), str(a.user_id)) for a in admins]
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
async def get_add_admin_pick_data(
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    config: FromDishka[Config],
    **kwargs: Any,
) -> dict[str, Any]:
    users = await user_service.list_users()
    candidates = [
        (_user_label(u.user_id, u.username), str(u.user_id))
        for u in users
        if not u.is_admin and not u.is_banned and u.user_id != config.bot.creator_id
    ]
    return {"candidates": candidates, "total_candidates": len(candidates)}


async def on_add_admin_pick(
    call: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    manager.dialog_data["candidate_user_id"] = int(item_id)
    await manager.switch_to(AdminPanelSG.add_admin_confirm)


@inject
async def get_add_admin_confirm_data(
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    **kwargs: Any,
) -> dict[str, Any]:
    user_id = dialog_manager.dialog_data.get("candidate_user_id")
    user = await user_service.get_by_id(user_id) if user_id else None
    if not user:
        return {}
    return {
        "username": _user_label(user.user_id, user.username),
        "user_id": user.user_id,
    }


@inject
async def on_add_admin_confirm(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    user_service: FromDishka[UserService],
    bot_service: FromDishka[BotService],
) -> None:
    user_id = manager.dialog_data.get("candidate_user_id")
    if not user_id:
        await call.answer("❌ Пользователь не выбран", show_alert=True)
        return

    updated = await user_service.set_admin(user_id, True)
    if not updated:
        await call.answer("❌ Не удалось назначить", show_alert=True)
        return

    await bot_service.notify_admin_assigned(user_id)
    await call.answer("⭐ Админ назначен", show_alert=True)
    await manager.switch_to(AdminPanelSG.admins_list)


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

    event_from_user = dialog_manager.middleware_data.get("event_from_user")
    is_creator = _is_creator(dialog_manager, config)
    is_self = bool(event_from_user and event_from_user.id == user.user_id)
    target_is_creator = user.user_id == config.bot.creator_id

    can_ban = not is_self and not target_is_creator and (is_creator or not user.is_admin)
    can_toggle_admin = is_creator and not target_is_creator

    return {
        "user_id": user.user_id,
        "username": _user_label(user.user_id, user.username),
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
    bot_service: FromDishka[BotService],
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
    if not updated:
        await call.answer("❌ Не удалось обновить", show_alert=True)
        return

    if updated.is_admin:
        await bot_service.notify_admin_assigned(updated.user_id)
    await call.answer("⭐ Назначен админом" if updated.is_admin else "🔻 Админ снят", show_alert=True)


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
    chats_data = [(c.title or str(c.chat_id), str(c.chat_id)) for c in chats]
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


@inject
async def get_groups_list_data(
    dialog_manager: DialogManager,
    study_group_service: FromDishka[StudyGroupService],
    config: FromDishka[Config],
    **kwargs: Any,
) -> dict[str, Any]:
    groups = await study_group_service.list_groups()
    groups_data = [(g.display_name, str(g.group_id)) for g in groups]
    return {
        "groups": groups_data,
        "total_groups": len(groups),
        "is_creator": _is_creator(dialog_manager, config),
    }


async def on_group_selected(
    call: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    manager.dialog_data["selected_group_id"] = int(item_id)
    await manager.switch_to(AdminPanelSG.group_detail)


@inject
async def get_group_detail_data(
    dialog_manager: DialogManager,
    study_group_service: FromDishka[StudyGroupService],
    config: FromDishka[Config],
    **kwargs: Any,
) -> dict[str, Any]:
    group_id = dialog_manager.dialog_data.get("selected_group_id")
    if not group_id:
        return {}

    group = await study_group_service.get_by_id(group_id)
    if not group:
        return {}

    return {
        "group_id": group.group_id,
        "alias": group.alias or "—",
        "created_at": group.created_at.strftime("%d.%m.%Y %H:%M"),
        "is_creator": _is_creator(dialog_manager, config),
    }


@inject
async def on_add_group_id_input(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
    study_group_service: FromDishka[StudyGroupService],
) -> None:
    text = (message.text or "").strip()

    if not (text.isdigit() and len(text) == 4):
        await message.answer("❌ ID группы — 4 цифры (например, 1125)")
        return

    group_id = int(text)
    if await study_group_service.get_by_id(group_id):
        await message.answer("ℹ️ Такая группа уже есть")
        await manager.switch_to(AdminPanelSG.groups_list)
        return

    manager.dialog_data["new_group_id"] = group_id
    await manager.switch_to(AdminPanelSG.group_add_alias)


async def _create_group(
    manager: DialogManager,
    study_group_service: StudyGroupService,
    group_id: int,
    alias: str | None,
) -> None:
    await study_group_service.create_group(group_id, alias)
    await manager.switch_to(AdminPanelSG.groups_list)


@inject
async def on_add_group_alias_input(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
    study_group_service: FromDishka[StudyGroupService],
) -> None:
    group_id = manager.dialog_data.get("new_group_id")
    if not group_id:
        await manager.switch_to(AdminPanelSG.groups_list)
        return

    alias = (message.text or "").strip()
    if len(alias) > 64:
        await message.answer("❌ Алиас слишком длинный (макс. 64 символа)")
        return

    await _create_group(manager, study_group_service, group_id, alias or None)
    await message.answer(f"✅ Группа {group_id} добавлена")


@inject
async def on_add_group_skip_alias(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    study_group_service: FromDishka[StudyGroupService],
) -> None:
    group_id = manager.dialog_data.get("new_group_id")
    if not group_id:
        await manager.switch_to(AdminPanelSG.groups_list)
        return

    await _create_group(manager, study_group_service, group_id, None)
    await call.answer("✅ Группа добавлена", show_alert=True)


@inject
async def on_group_delete_confirm(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    study_group_service: FromDishka[StudyGroupService],
) -> None:
    group_id = manager.dialog_data.get("selected_group_id")
    if not group_id:
        await call.answer("❌ Группа не выбрана", show_alert=True)
        return

    removed = await study_group_service.delete_group(group_id)
    await call.answer("🗑 Группа удалена" if removed else "❌ Не удалось удалить", show_alert=True)
    await manager.switch_to(AdminPanelSG.groups_list)


admin_panel_dialog = Dialog(
    Window(
        Format(
            "🛠 <b>Админ-панель</b>\n\n"
            "<pre>👤 {total_users} юзеров | 🏫 {total_chats} чатов</pre>\n\n"
            "Выберите раздел:"
        ),
        SwitchTo(Const("👤 Пользователи"), id="sec_users", state=AdminPanelSG.users_list),
        SwitchTo(Const("🛡 Админы"), id="sec_admins", state=AdminPanelSG.admins_list, when="is_creator"),
        Row(
            SwitchTo(Const("📚 Группы"), id="sec_groups", state=AdminPanelSG.groups_list),
            SwitchTo(Const("🏫 Чаты"), id="sec_chats", state=AdminPanelSG.chats_list),
        ),
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
            hide_on_single_page=True,
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
            hide_on_single_page=True,
        ),
        SwitchTo(Const("➕ Добавить админа"), id="add_admin", state=AdminPanelSG.add_admin_pick),
        SwitchTo(Const("⬅️ Назад"), id="back_main_admins", state=AdminPanelSG.main),
        state=AdminPanelSG.admins_list,
        getter=get_admins_list_data,
    ),
    Window(
        Format("➕ <b>Добавить админа</b> | Кандидатов: {total_candidates}\n\nВыберите пользователя:"),
        ScrollingGroup(
            Select(
                Format("{item[0]}"),
                id="candidate_select",
                item_id_getter=lambda x: x[1],
                items="candidates",
                on_click=on_add_admin_pick,
            ),
            id="candidates_scroll",
            width=1,
            height=7,
            hide_on_single_page=True,
        ),
        SwitchTo(Const("⬅️ Назад"), id="back_admins_pick", state=AdminPanelSG.admins_list),
        state=AdminPanelSG.add_admin_pick,
        getter=get_add_admin_pick_data,
    ),
    Window(
        Format("Назначить {username} <code>({user_id})</code> админом?"),
        Button(Const("✅ Назначить"), id="confirm_add_admin", on_click=on_add_admin_confirm),
        SwitchTo(Const("⬅️ Назад"), id="back_pick", state=AdminPanelSG.add_admin_pick),
        state=AdminPanelSG.add_admin_confirm,
        getter=get_add_admin_confirm_data,
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
            hide_on_single_page=True,
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
    Window(
        Format("📚 <b>Группы</b> | Всего: {total_groups}"),
        ScrollingGroup(
            Select(
                Format("{item[0]}"),
                id="group_select",
                item_id_getter=lambda x: x[1],
                items="groups",
                on_click=on_group_selected,
            ),
            id="groups_scroll",
            width=1,
            height=7,
            hide_on_single_page=True,
        ),
        SwitchTo(Const("➕ Добавить группу"), id="add_group", state=AdminPanelSG.group_add_id, when="is_creator"),
        SwitchTo(Const("⬅️ Назад"), id="back_main_groups", state=AdminPanelSG.main),
        state=AdminPanelSG.groups_list,
        getter=get_groups_list_data,
    ),
    Window(
        Format(
            "📚 <b>Группа</b>\n\n"
            "<blockquote>• ID: <code>{group_id}</code>\n"
            "• Алиас: {alias}\n"
            "• Создана: {created_at}</blockquote>"
        ),
        SwitchTo(Const("🗑 Удалить группу"), id="del_group", state=AdminPanelSG.group_del_confirm, when="is_creator"),
        SwitchTo(Const("⬅️ Назад"), id="back_groups", state=AdminPanelSG.groups_list),
        state=AdminPanelSG.group_detail,
        getter=get_group_detail_data,
    ),
    Window(
        Format("Удалить группу <code>{group_id}</code> ({alias})?"),
        Button(Const("✅ Удалить"), id="confirm_del_group", on_click=on_group_delete_confirm),
        SwitchTo(Const("⬅️ Назад"), id="back_group_detail", state=AdminPanelSG.group_detail),
        state=AdminPanelSG.group_del_confirm,
        getter=get_group_detail_data,
    ),
    Window(
        Const(
            "➕ <b>Новая группа</b>\n\n"
            "Введите ID группы — 4 цифры (например, 1125):"
        ),
        MessageInput(on_add_group_id_input, content_types=["text"]),
        SwitchTo(Const("⬅️ Назад"), id="back_groups_add", state=AdminPanelSG.groups_list),
        state=AdminPanelSG.group_add_id,
    ),
    Window(
        Const(
            "➕ <b>Новая группа</b>\n\n"
            "Введите алиас для группы или пропустите:"
        ),
        MessageInput(on_add_group_alias_input, content_types=["text"]),
        Button(Const("⏭ Без алиаса"), id="skip_alias", on_click=on_add_group_skip_alias),
        SwitchTo(Const("⬅️ Назад"), id="back_group_id", state=AdminPanelSG.group_add_id),
        state=AdminPanelSG.group_add_alias,
    ),
)
