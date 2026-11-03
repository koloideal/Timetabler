import logging
import re
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

from timetabler.application.services.group_chat import GroupChatService
from timetabler.application.services.settings import (
    SETTING_CREDENTIALS_PATH,
    SETTING_DATE_CELL,
    SETTING_POLL_INTERVAL,
    SETTING_SCHEDULE_RANGE,
    SettingsService,
)
from timetabler.application.services.sheets import SheetsService
from timetabler.application.services.study_group import StudyGroupService
from timetabler.application.services.user import UserService
from timetabler.infrastructure.config.app import AppConfig
from timetabler.infrastructure.config.models import Config
from timetabler.infrastructure.sheets import GoogleSheetsClient, SheetAccessError

logger = logging.getLogger(__name__)

SPREADSHEET_ID_RE = re.compile(r"[A-Za-z0-9_-]+")
SPREADSHEET_URL_RE = re.compile(r"/d/([A-Za-z0-9_-]+)")
A1_RANGE_RE = re.compile(r"[A-Za-z]+\d+:[A-Za-z]+\d+")
A1_CELL_RE = re.compile(r"[A-Za-z]+\d+")

SETTING_FIELDS = {
    SETTING_CREDENTIALS_PATH: "путь к ключу",
    SETTING_SCHEDULE_RANGE: "диапазон расписания",
    SETTING_DATE_CELL: "ячейка даты",
    SETTING_POLL_INTERVAL: "интервал опроса, сек",
}


class AdminPanelSG(StatesGroup):
    main = State()
    users_list = State()
    user_detail = State()
    chats_list = State()
    chat_detail = State()
    groups_list = State()
    group_detail = State()
    group_del_confirm = State()
    group_add_id = State()
    group_add_alias = State()
    sheets_list = State()
    sheet_detail = State()
    sheet_set_input = State()
    sheets_settings = State()
    setting_input = State()


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
    **kwargs: Any,
) -> dict[str, Any]:
    users = await user_service.list_users()
    chats = await group_chat_service.list_chats()
    return {
        "total_users": len(users),
        "total_chats": len(chats),
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
        badge = "👑" if user.user_id == config.bot.creator_id else "🚫" if user.is_banned else ""
        users_data.append((f"{badge}{_user_label(user.user_id, user.username)}".strip(), str(user.user_id)))
    return {"users": users_data, "total_users": len(users)}


async def on_user_selected(
    call: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    manager.dialog_data["selected_user_id"] = int(item_id)
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

    event_from_user = dialog_manager.middleware_data.get("event_from_user")
    is_self = bool(event_from_user and event_from_user.id == user.user_id)
    target_is_creator = user.user_id == config.bot.creator_id

    can_ban = not is_self and not target_is_creator

    return {
        "user_id": user.user_id,
        "username": _user_label(user.user_id, user.username),
        "registered_at": user.created_at.strftime("%d.%m.%Y %H:%M"),
        "groups": _format_groups(user.groups),
        "ban_status": "🚫 заблокирован" if user.is_banned else "✅ активен",
        "ban_button_text": "✅ Разбанить" if user.is_banned else "🚫 Забанить",
        "can_ban": can_ban,
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

    updated = await user_service.set_banned(target.user_id, not target.is_banned)
    if updated:
        await call.answer("✅ Разбанен" if not updated.is_banned else "🚫 Забанен", show_alert=True)
    else:
        await call.answer("❌ Не удалось обновить", show_alert=True)


async def on_detail_back(call: CallbackQuery, button: Button, manager: DialogManager) -> None:
    await manager.switch_to(AdminPanelSG.users_list)


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
    groups_alias = [(g.display_name, str(g.group_id)) for g in groups if g.alias]
    groups_plain = [(str(g.group_id), str(g.group_id)) for g in groups if not g.alias]
    return {
        "groups_alias": groups_alias,
        "groups_plain": groups_plain,
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
    app_config: FromDishka[AppConfig],
) -> None:
    group_id = manager.dialog_data.get("new_group_id")
    if not group_id:
        await manager.switch_to(AdminPanelSG.groups_list)
        return

    alias = (message.text or "").strip()
    if len(alias) > app_config.max_alias_length:
        await message.answer(f"❌ Алиас слишком длинный (макс. {app_config.max_alias_length} символа)")
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


@inject
async def get_sheets_list_data(
    dialog_manager: DialogManager,
    sheets_service: FromDishka[SheetsService],
    app_config: FromDishka[AppConfig],
    **kwargs: Any,
) -> dict[str, Any]:
    sources = {s.weekday: s for s in await sheets_service.list_sources()}
    sheets_data = []
    for weekday in range(6):
        source = sources.get(weekday)
        spreadsheet_id = source.spreadsheet_id if source else None
        sheets_data.append((
            f"{app_config.weekdays_short[weekday]} — {spreadsheet_id or 'не задана'}",
            str(weekday),
        ))
    return {"sheets": sheets_data}


async def on_weekday_selected(
    call: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    manager.dialog_data["selected_weekday"] = int(item_id)
    await manager.switch_to(AdminPanelSG.sheet_detail)


@inject
async def get_sheet_detail_data(
    dialog_manager: DialogManager,
    sheets_service: FromDishka[SheetsService],
    app_config: FromDishka[AppConfig],
    **kwargs: Any,
) -> dict[str, Any]:
    weekday = dialog_manager.dialog_data.get("selected_weekday")
    if weekday is None:
        return {}

    source = await sheets_service.get_source(weekday)
    return {
        "weekday_name": app_config.weekdays_short[weekday],
        "spreadsheet_id": (source.spreadsheet_id if source else None) or "—",
        "last_header": (source.last_header if source else None) or "—",
        "has_id": bool(source and source.spreadsheet_id),
    }


@inject
async def on_sheet_clear(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    sheets_service: FromDishka[SheetsService],
) -> None:
    weekday = manager.dialog_data.get("selected_weekday")
    if weekday is None:
        await call.answer("❌ День не выбран", show_alert=True)
        return

    await sheets_service.set_spreadsheet(weekday, None)
    await call.answer("🗑 ID очищен", show_alert=True)
    await manager.switch_to(AdminPanelSG.sheets_list)


@inject
async def on_sheet_id_input(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
    sheets_service: FromDishka[SheetsService],
    settings_service: FromDishka[SettingsService],
    sheets_client: FromDishka[GoogleSheetsClient],
) -> None:
    weekday = manager.dialog_data.get("selected_weekday")
    if weekday is None:
        await manager.switch_to(AdminPanelSG.sheets_list)
        return

    text = (message.text or "").strip()
    url_match = SPREADSHEET_URL_RE.search(text)
    spreadsheet_id = url_match.group(1) if url_match else text

    if not SPREADSHEET_ID_RE.fullmatch(spreadsheet_id):
        await message.answer(
            "❌ Не похоже на ID таблицы.\n"
            "Пришлите ID или ссылку вида .../d/<ID>/edit"
        )
        return

    settings = await settings_service.get_sheets_settings()
    if not settings.credentials_path:
        await message.answer("❌ Сначала задайте путь к ключу в ⚙️ Настройки")
        return
    try:
        sheets_client.configure(settings.credentials_path)
    except Exception as e:
        await message.answer(f"❌ Не удалось загрузить ключ: {e}")
        return

    try:
        await sheets_client.read_values(spreadsheet_id, settings.date_cell)
    except SheetAccessError as e:
        await message.answer(
            f"❌ Таблица недоступна: {e}\n\n"
            f"Расшарьте её на сервисный аккаунт:\n"
            f"<code>{sheets_client.service_account_email}</code>"
        )
        return
    except Exception as e:
        await message.answer(f"❌ Не удалось прочитать таблицу: {e}")
        return

    await sheets_service.set_spreadsheet(weekday, spreadsheet_id)
    await message.answer("✅ ID сохранён, таблица доступна сервисному аккаунту")
    await manager.switch_to(AdminPanelSG.sheets_list)


@inject
async def get_sheets_settings_data(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    settings = await settings_service.get_sheets_settings()
    values = {
        SETTING_CREDENTIALS_PATH: settings.credentials_path or "—",
        SETTING_SCHEDULE_RANGE: settings.schedule_range,
        SETTING_DATE_CELL: settings.date_cell,
        SETTING_POLL_INTERVAL: str(settings.poll_interval_seconds),
    }
    items = [(f"{label} = {values[key]}", key) for key, label in SETTING_FIELDS.items()]
    return {"settings_items": items}


async def on_setting_selected(
    call: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    manager.dialog_data["setting_key"] = item_id
    await manager.switch_to(AdminPanelSG.setting_input)


@inject
async def get_setting_input_data(
    dialog_manager: DialogManager,
    **kwargs: Any,
) -> dict[str, Any]:
    key = dialog_manager.dialog_data.get("setting_key") or ""
    return {"setting_label": SETTING_FIELDS.get(key, "?")}


@inject
async def on_setting_input(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    sheets_client: FromDishka[GoogleSheetsClient],
) -> None:
    key = manager.dialog_data.get("setting_key")
    if key not in SETTING_FIELDS:
        await manager.switch_to(AdminPanelSG.sheets_settings)
        return

    text = (message.text or "").strip()

    if key == SETTING_CREDENTIALS_PATH:
        try:
            sheets_client.configure(text)
        except Exception as e:
            await message.answer(f"❌ Не удалось загрузить ключ: {e}")
            return
        await settings_service.set(key, text)
        await message.answer(
            f"✅ Путь сохранён, аккаунт: <code>{sheets_client.service_account_email}</code>"
        )
    elif key == SETTING_SCHEDULE_RANGE:
        if not A1_RANGE_RE.fullmatch(text):
            await message.answer("❌ Диапазон вида A1:I100, без имени листа")
            return
        await settings_service.set(key, text.upper())
        await message.answer("✅ Диапазон сохранён")
    elif key == SETTING_DATE_CELL:
        if not A1_CELL_RE.fullmatch(text):
            await message.answer("❌ Ячейка вида A1")
            return
        await settings_service.set(key, text.upper())
        await message.answer("✅ Ячейка сохранена")
    elif key == SETTING_POLL_INTERVAL:
        if not text.isdigit() or int(text) < 10:
            await message.answer("❌ Интервал — целое число секунд (мин. 10)")
            return
        await settings_service.set(key, text)
        await message.answer("✅ Интервал сохранён")

    await manager.switch_to(AdminPanelSG.sheets_settings)


admin_panel_dialog = Dialog(
    Window(
        Format(
            "🛠 <b>АДМИН-ПАНЕЛЬ</b>\n"
            "<pre>━━━━━━━━━━━━━━━━━━\n"
            "ЮЗЕРОВ    {total_users}\n"
            "ЧАТОВ     {total_chats}\n"
            "━━━━━━━━━━━━━━━━━━</pre>\n"
            "Выберите раздел:"
        ),
        SwitchTo(Const("👤 Пользователи"), id="sec_users", state=AdminPanelSG.users_list),
        SwitchTo(Const("📊 Таблицы"), id="sec_sheets", state=AdminPanelSG.sheets_list),
        Row(
            SwitchTo(Const("📚 Группы"), id="sec_groups", state=AdminPanelSG.groups_list),
            SwitchTo(Const("🏫 Чаты"), id="sec_chats", state=AdminPanelSG.chats_list),
        ),
        state=AdminPanelSG.main,
        getter=get_admin_main_data,
    ),
    Window(
        Format("👤 <b>ПОЛЬЗОВАТЕЛИ</b> · {total_users}\n━━━━━━━━━━━━━━━━━━"),
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
        Format(
            "👤 <b>ПОЛЬЗОВАТЕЛЬ</b>\n"
            "<pre>━━━━━━━━━━━━━━━━━━\n"
            "ID        {user_id}\n"
            "USERNAME  {username}\n"
            "REG       {registered_at}\n"
            "ГРУППЫ    {groups}\n"
            "СТАТУС    {ban_status}\n"
            "━━━━━━━━━━━━━━━━━━</pre>"
        ),
        Button(
            Format("{ban_button_text}"),
            id="ban_toggle",
            on_click=on_ban_toggle,
            when="can_ban",
        ),
        Button(Const("⬅️ Назад"), id="back_to_list", on_click=on_detail_back),
        state=AdminPanelSG.user_detail,
        getter=get_user_detail_data,
    ),
    Window(
        Format("🏫 <b>ЧАТЫ</b> · {total_chats}\n━━━━━━━━━━━━━━━━━━"),
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
            "🏫 <b>ЧАТ</b>\n"
            "<pre>━━━━━━━━━━━━━━━━━━\n"
            "НАЗВАНИЕ  {title}\n"
            "ID        {chat_id}\n"
            "ДОБАВЛЕН  {added_at}\n"
            "ГРУППЫ    {groups}\n"
            "━━━━━━━━━━━━━━━━━━</pre>"
        ),
        SwitchTo(Const("⬅️ Назад"), id="back_to_chats", state=AdminPanelSG.chats_list),
        state=AdminPanelSG.chat_detail,
        getter=get_chat_detail_data,
    ),
    Window(
        Format("📚 <b>ГРУППЫ</b> · {total_groups}\n━━━━━━━━━━━━━━━━━━"),
        ScrollingGroup(
            Select(
                Format("{item[0]}"),
                id="group_select_a",
                item_id_getter=lambda x: x[1],
                items="groups_alias",
                on_click=on_group_selected,
            ),
            id="groups_alias_scroll",
            width=1,
            height=4,
            hide_on_single_page=True,
        ),
        ScrollingGroup(
            Select(
                Format("{item[0]}"),
                id="group_select_p",
                item_id_getter=lambda x: x[1],
                items="groups_plain",
                on_click=on_group_selected,
            ),
            id="groups_plain_scroll",
            width=3,
            height=6,
            hide_on_single_page=True,
        ),
        SwitchTo(Const("➕ Добавить группу"), id="add_group", state=AdminPanelSG.group_add_id, when="is_creator"),
        SwitchTo(Const("⬅️ Назад"), id="back_main_groups", state=AdminPanelSG.main),
        state=AdminPanelSG.groups_list,
        getter=get_groups_list_data,
    ),
    Window(
        Format(
            "📚 <b>ГРУППА</b>\n"
            "<pre>━━━━━━━━━━━━━━━━━━\n"
            "ID        {group_id}\n"
            "АЛИАС     {alias}\n"
            "СОЗДАНА   {created_at}\n"
            "━━━━━━━━━━━━━━━━━━</pre>"
        ),
        SwitchTo(Const("🗑 Удалить группу"), id="del_group", state=AdminPanelSG.group_del_confirm, when="is_creator"),
        SwitchTo(Const("⬅️ Назад"), id="back_groups", state=AdminPanelSG.groups_list),
        state=AdminPanelSG.group_detail,
        getter=get_group_detail_data,
    ),
    Window(
        Format("🗑 <b>УДАЛИТЬ ГРУППУ?</b>\n<pre>ID      {group_id}\nАЛИАС   {alias}</pre>"),
        Button(Const("✅ Удалить"), id="confirm_del_group", on_click=on_group_delete_confirm),
        SwitchTo(Const("⬅️ Назад"), id="back_group_detail", state=AdminPanelSG.group_detail),
        state=AdminPanelSG.group_del_confirm,
        getter=get_group_detail_data,
    ),
    Window(
        Const(
            "➕ <b>НОВАЯ ГРУППА</b>\n━━━━━━━━━━━━━━━━━━\n"
            "Введите ID группы — 4 цифры (например, 1125):"
        ),
        MessageInput(on_add_group_id_input, content_types=["text"]),
        SwitchTo(Const("⬅️ Назад"), id="back_groups_add", state=AdminPanelSG.groups_list),
        state=AdminPanelSG.group_add_id,
    ),
    Window(
        Const(
            "➕ <b>НОВАЯ ГРУППА</b>\n━━━━━━━━━━━━━━━━━━\n"
            "Введите алиас для группы или пропустите:"
        ),
        MessageInput(on_add_group_alias_input, content_types=["text"]),
        Button(Const("⏭ Без алиаса"), id="skip_alias", on_click=on_add_group_skip_alias),
        SwitchTo(Const("⬅️ Назад"), id="back_group_id", state=AdminPanelSG.group_add_id),
        state=AdminPanelSG.group_add_alias,
    ),
    Window(
        Const("📊 <b>ТАБЛИЦЫ</b>\n━━━━━━━━━━━━━━━━━━\nВыберите день недели:"),
        ScrollingGroup(
            Select(
                Format("{item[0]}"),
                id="sheet_select",
                item_id_getter=lambda x: x[1],
                items="sheets",
                on_click=on_weekday_selected,
            ),
            id="sheets_scroll",
            width=1,
            height=6,
            hide_on_single_page=True,
        ),
        SwitchTo(Const("⚙️ Настройки"), id="sheets_settings", state=AdminPanelSG.sheets_settings),
        SwitchTo(Const("⬅️ Назад"), id="back_main_sheets", state=AdminPanelSG.main),
        state=AdminPanelSG.sheets_list,
        getter=get_sheets_list_data,
    ),
    Window(
        Format(
            "📊 <b>ТАБЛИЦА · {weekday_name}</b>\n"
            "<pre>━━━━━━━━━━━━━━━━━━\n"
            "ID        {spreadsheet_id}\n"
            "ШАПКА     {last_header}\n"
            "━━━━━━━━━━━━━━━━━━</pre>"
        ),
        SwitchTo(Const("✏️ Задать ID"), id="set_sheet_id", state=AdminPanelSG.sheet_set_input),
        Button(Const("🗑 Очистить ID"), id="clear_sheet_id", on_click=on_sheet_clear, when="has_id"),
        SwitchTo(Const("⬅️ Назад"), id="back_sheets", state=AdminPanelSG.sheets_list),
        state=AdminPanelSG.sheet_detail,
        getter=get_sheet_detail_data,
    ),
    Window(
        Const(
            "✏️ <b>ID ТАБЛИЦЫ</b>\n━━━━━━━━━━━━━━━━━━\n"
            "Пришлите ID таблицы или ссылку вида\n"
            "docs.google.com/spreadsheets/d/<ID>/edit"
        ),
        MessageInput(on_sheet_id_input, content_types=["text"]),
        SwitchTo(Const("⬅️ Назад"), id="back_sheet_detail", state=AdminPanelSG.sheet_detail),
        state=AdminPanelSG.sheet_set_input,
    ),
    Window(
        Const("⚙️ <b>НАСТРОЙКИ SHEETS</b>\n━━━━━━━━━━━━━━━━━━\nВыберите параметр:"),
        ScrollingGroup(
            Select(
                Format("{item[0]}"),
                id="setting_select",
                item_id_getter=lambda x: x[1],
                items="settings_items",
                on_click=on_setting_selected,
            ),
            id="settings_scroll",
            width=1,
            height=5,
            hide_on_single_page=True,
        ),
        SwitchTo(Const("⬅️ Назад"), id="back_sheets_settings", state=AdminPanelSG.sheets_list),
        state=AdminPanelSG.sheets_settings,
        getter=get_sheets_settings_data,
    ),
    Window(
        Format(
            "✏️ <b>{setting_label}</b>\n━━━━━━━━━━━━━━━━━━\n"
            "Пришлите новое значение:"
        ),
        MessageInput(on_setting_input, content_types=["text"]),
        SwitchTo(Const("⬅️ Назад"), id="back_setting", state=AdminPanelSG.sheets_settings),
        state=AdminPanelSG.setting_input,
        getter=get_setting_input_data,
    ),
)
