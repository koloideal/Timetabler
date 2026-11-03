import logging
import re
from datetime import date
from typing import Any

from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramAPIError
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
from timetabler.application.services.broadcast import BroadcastService
from timetabler.application.services.channel import ChannelService
from timetabler.application.services.group_chat import GroupChatService
from timetabler.application.services.poller import next_study_day
from timetabler.application.services.settings import SettingsService
from timetabler.application.services.sheets import SheetsService
from timetabler.application.services.study_group import StudyGroupService
from timetabler.application.services.user import UserService
from timetabler.infrastructure.config.app import AppConfig
from timetabler.infrastructure.config.models import Config
from timetabler.infrastructure.sheets import GoogleSheetsClient, SheetAccessError


class AdminPanelSG(StatesGroup):
    main = State()
    users_list = State()
    user_detail = State()
    chats_list = State()
    chat_detail = State()
    groups_list = State()
    group_detail = State()
    group_del_confirm = State()
    group_alias_edit = State()
    sheets_list = State()
    sheet_detail = State()
    sheet_set_input = State()
    sheets_settings = State()
    setting_input = State()
    schedule_view = State()
    channels_list = State()
    channel_detail = State()


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




_CHANNEL_STATUS_ICONS = {"pending": "⏳", "approved": "✅", "disabled": "🔕"}
_CHANNEL_STATUS_LABELS = {"pending": "⏳ ожидает", "approved": "✅ включён", "disabled": "🔕 отключён"}


@inject
async def get_channels_list_data(
    dialog_manager: DialogManager,
    channel_service: FromDishka[ChannelService],
    **kwargs: Any,
) -> dict[str, Any]:
    channels = await channel_service.list_channels()
    channels_data = [
        (f"{_CHANNEL_STATUS_ICONS.get(c.status, '❔')} {c.title or c.chat_id}", str(c.chat_id))
        for c in channels
    ]
    return {"channels": channels_data, "total_channels": len(channels)}


async def on_channel_selected(
    call: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    manager.dialog_data["selected_channel_id"] = int(item_id)
    await manager.switch_to(AdminPanelSG.channel_detail)


@inject
async def get_channel_detail_data(
    dialog_manager: DialogManager,
    channel_service: FromDishka[ChannelService],
    **kwargs: Any,
) -> dict[str, Any]:
    chat_id = dialog_manager.dialog_data.get("selected_channel_id")
    channel = await channel_service.get_by_id(chat_id) if chat_id else None
    if not channel:
        return {}
    return {
        "chat_id": channel.chat_id,
        "title": channel.title or "—",
        "status": _CHANNEL_STATUS_LABELS.get(channel.status, channel.status),
        "added_at": channel.created_at.strftime("%d.%m.%Y %H:%M"),
        "is_pending": channel.status == "pending",
        "is_approved": channel.status == "approved",
        "is_disabled": channel.status == "disabled",
    }


@inject
async def on_channel_approve_btn(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    channel_service: FromDishka[ChannelService],
) -> None:
    chat_id = manager.dialog_data.get("selected_channel_id")
    if chat_id is None or call.bot is None:
        return
    await channel_service.approve(chat_id)
    try:
        await call.bot.send_message(chat_id, "✅ Бот подключён — сюда будет приходить расписание.")
    except TelegramAPIError:
        pass
    await call.answer("✅ Одобрен")
    await manager.update({})


@inject
async def on_channel_enable(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    channel_service: FromDishka[ChannelService],
) -> None:
    chat_id = manager.dialog_data.get("selected_channel_id")
    if chat_id is None:
        return
    await channel_service.approve(chat_id)
    await call.answer("🔔 Канал включён")
    await manager.update({})


@inject
async def on_channel_disable(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    channel_service: FromDishka[ChannelService],
) -> None:
    chat_id = manager.dialog_data.get("selected_channel_id")
    if chat_id is None:
        return
    await channel_service.disable(chat_id)
    await call.answer("🔕 Канал отключён")
    await manager.update({})


@inject
async def on_channel_schedule(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    broadcast_service: FromDishka[BroadcastService],
) -> None:
    chat_id = manager.dialog_data.get("selected_channel_id")
    if chat_id is None:
        return
    try:
        sent = await broadcast_service.send_channel_schedule(chat_id, next_study_day(date.today()))
    except TelegramAPIError as e:
        await call.answer(f"Не смог отправить: {e.message}", show_alert=True)
        return
    if not sent:
        await call.answer("Нет расписания", show_alert=True)
        return
    await call.answer("📅 Отправлено")


@inject
async def on_channel_delete(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    channel_service: FromDishka[ChannelService],
) -> None:
    chat_id = manager.dialog_data.get("selected_channel_id")
    if chat_id is None:
        return
    if call.bot is not None:
        try:
            await call.bot.leave_chat(chat_id)
        except TelegramAPIError:
            pass
    await channel_service.remove(chat_id)
    await call.answer("🗑 Удалён, я вышел из канала")
    await manager.switch_to(AdminPanelSG.channels_list)


@inject
async def get_groups_list_data(
    dialog_manager: DialogManager,
    study_group_service: FromDishka[StudyGroupService],
    **kwargs: Any,
) -> dict[str, Any]:
    groups = await study_group_service.list_groups()
    groups_alias = [(g.display_name, str(g.group_id)) for g in groups if g.alias]
    groups_plain = [(str(g.group_id), str(g.group_id)) for g in groups if not g.alias]
    return {
        "groups_alias": groups_alias,
        "groups_plain": groups_plain,
        "total_groups": len(groups),
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
async def on_edit_group_alias_input(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
    study_group_service: FromDishka[StudyGroupService],
    app_config: FromDishka[AppConfig],
) -> None:
    group_id = manager.dialog_data.get("selected_group_id")
    if not group_id:
        await manager.switch_to(AdminPanelSG.groups_list)
        return

    alias = (message.text or "").strip()
    if len(alias) > app_config.max_alias_length:
        await message.answer(f"❌ Алиас слишком длинный (макс. {app_config.max_alias_length} символа)")
        return

    await study_group_service.set_alias(group_id, alias or None)
    await message.answer(f"✅ Алиас для {group_id} сохранён")
    await manager.switch_to(AdminPanelSG.group_detail)


@inject
async def on_group_alias_clear(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    study_group_service: FromDishka[StudyGroupService],
) -> None:
    group_id = manager.dialog_data.get("selected_group_id")
    if not group_id:
        await manager.switch_to(AdminPanelSG.groups_list)
        return

    await study_group_service.set_alias(group_id, None)
    await call.answer("🗑 Алиас убран", show_alert=True)
    await manager.switch_to(AdminPanelSG.group_detail)


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
    app_config: FromDishka[AppConfig],
) -> None:
    weekday = manager.dialog_data.get("selected_weekday")
    if weekday is None:
        await manager.switch_to(AdminPanelSG.sheets_list)
        return

    text = (message.text or "").strip()
    url_match = re.search(app_config.sheets_settings.spreadsheet_url_pattern, text)
    spreadsheet_id = url_match.group(1) if url_match else text

    if not re.fullmatch(app_config.sheets_settings.spreadsheet_id_pattern, spreadsheet_id):
        await message.answer(
            "❌ Не похоже на ID таблицы.\n"
            "Пришлите ID или ссылку вида .../d/&lt;ID&gt;/edit"
        )
        return

    settings = await settings_service.get_sheets_settings()
    try:
        await sheets_client.read_values(spreadsheet_id, settings.date_cell)
    except SheetAccessError as e:
        text = f"❌ Таблица недоступна: {e}"
        if sheets_client.service_account_email:
            text += (
                f"\n\nРасшарьте её на сервисный аккаунт:\n"
                f"<code>{sheets_client.service_account_email}</code>"
            )
        await message.answer(text)
        return
    except Exception:
        logging.getLogger(__name__).exception(
            "Unexpected error reading sheet %s", spreadsheet_id
        )
        await message.answer("❌ Не удалось прочитать таблицу (подробности в логах)")
        return

    await sheets_service.set_spreadsheet(weekday, spreadsheet_id)
    await message.answer("✅ ID сохранён, таблица доступна сервисному аккаунту")
    await manager.switch_to(AdminPanelSG.sheets_list)


@inject
async def get_schedule_view_data(
    dialog_manager: DialogManager,
    broadcast_service: FromDishka[BroadcastService],
    study_group_service: FromDishka[StudyGroupService],
    app_config: FromDishka[AppConfig],
    **kwargs: Any,
) -> dict[str, Any]:
    target = next_study_day(date.today())
    preview = await broadcast_service.build_preview(target)
    groups = await study_group_service.list_groups()
    weekday = app_config.weekdays_short[target.weekday()]
    return {
        "schedule_date": f"{target.strftime('%d.%m.%Y')} ({weekday})",
        "groups": preview.groups if preview else 0,
        "lessons": preview.lessons if preview else 0,
        "has_schedule": preview is not None,
        "schedule_groups": [("📚 Все группы", "all")]
        + [(g.display_name, str(g.group_id)) for g in groups],
    }


@inject
async def on_schedule_group_selected(
    call: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
    broadcast_service: FromDishka[BroadcastService],
    bot_service: FromDishka[BotService],
) -> None:
    group_id = None if item_id == "all" else int(item_id)
    preview = await broadcast_service.build_preview(next_study_day(date.today()), group_id)
    if preview is None:
        await call.answer("Нет расписания", show_alert=True)
        return
    await bot_service.send_rich_to_creator(preview.markdown)
    await call.answer()


@inject
async def get_sheets_settings_data(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    app_config: FromDishka[AppConfig],
    **kwargs: Any,
) -> dict[str, Any]:
    settings = await settings_service.get_sheets_settings()
    cfg = app_config.sheets_settings
    values = {
        cfg.schedule_range_key: settings.schedule_range,
        cfg.date_cell_key: settings.date_cell,
        cfg.poll_interval_key: str(settings.poll_interval_seconds),
        cfg.confirmation_key: "вкл" if settings.require_confirmation else "выкл",
    }
    items = [(f"{label} = {values[key]}", key) for key, label in cfg.fields]
    return {"settings_items": items}


@inject
async def on_setting_selected(
    call: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
    settings_service: FromDishka[SettingsService],
    app_config: FromDishka[AppConfig],
) -> None:
    cfg = app_config.sheets_settings
    if item_id == cfg.confirmation_key:
        settings = await settings_service.get_sheets_settings()
        enabled = not settings.require_confirmation
        await settings_service.set(cfg.confirmation_key, "1" if enabled else "0")
        await call.answer(
            "🔔 Подтверждение вкл" if enabled else "🔕 Подтверждение выкл",
            show_alert=True,
        )
        return
    manager.dialog_data["setting_key"] = item_id
    await manager.switch_to(AdminPanelSG.setting_input)


@inject
async def get_setting_input_data(
    dialog_manager: DialogManager,
    app_config: FromDishka[AppConfig],
    **kwargs: Any,
) -> dict[str, Any]:
    key = dialog_manager.dialog_data.get("setting_key") or ""
    return {"setting_label": dict(app_config.sheets_settings.fields).get(key, "?")}


@inject
async def on_setting_input(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    app_config: FromDishka[AppConfig],
) -> None:
    cfg = app_config.sheets_settings
    key = manager.dialog_data.get("setting_key")
    if key not in dict(cfg.text_fields):
        await manager.switch_to(AdminPanelSG.sheets_settings)
        return

    text = (message.text or "").strip()

    if key == cfg.schedule_range_key:
        if not re.fullmatch(cfg.a1_range_pattern, text):
            await message.answer("❌ Диапазон вида A1:I100, без имени листа")
            return
        await settings_service.set(key, text.upper())
        await message.answer("✅ Диапазон сохранён")
    elif key == cfg.date_cell_key:
        if not re.fullmatch(cfg.a1_cell_pattern, text):
            await message.answer("❌ Ячейка вида A1")
            return
        await settings_service.set(key, text.upper())
        await message.answer("✅ Ячейка сохранена")
    elif key == cfg.poll_interval_key:
        if not text.isdigit() or int(text) < cfg.min_poll_interval_seconds:
            await message.answer(
                f"❌ Интервал — целое число секунд (мин. {cfg.min_poll_interval_seconds})"
            )
            return
        await settings_service.set(key, text)
        await message.answer("✅ Интервал сохранён")

    await manager.switch_to(AdminPanelSG.sheets_settings)


def build_admin_panel_dialog() -> Dialog:
    return Dialog(
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
            Row(
                SwitchTo(Const("📊 Таблицы"), id="sec_sheets", state=AdminPanelSG.sheets_list),
                SwitchTo(Const("📚 Группы"), id="sec_groups", state=AdminPanelSG.groups_list),
            ),
            SwitchTo(Const("📅 Расписание"), id="sec_schedule", state=AdminPanelSG.schedule_view),
            Row(
                SwitchTo(Const("🏫 Чаты"), id="sec_chats", state=AdminPanelSG.chats_list),
                SwitchTo(Const("📢 Каналы"), id="sec_channels", state=AdminPanelSG.channels_list),
            ),
            SwitchTo(Const("⚙️ Настройки"), id="sec_settings", state=AdminPanelSG.sheets_settings),
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
            Format("📢 <b>КАНАЛЫ</b> · {total_channels}\n━━━━━━━━━━━━━━━━━━"),
            ScrollingGroup(
                Select(
                    Format("{item[0]}"),
                    id="channel_select",
                    item_id_getter=lambda x: x[1],
                    items="channels",
                    on_click=on_channel_selected,
                ),
                id="channels_scroll",
                width=1,
                height=7,
                hide_on_single_page=True,
            ),
            SwitchTo(Const("⬅️ Назад"), id="back_main_channels", state=AdminPanelSG.main),
            state=AdminPanelSG.channels_list,
            getter=get_channels_list_data,
        ),
        Window(
            Format(
                "📢 <b>КАНАЛ</b>\n"
                "<pre>━━━━━━━━━━━━━━━━━━\n"
                "НАЗВАНИЕ  {title}\n"
                "ID        {chat_id}\n"
                "СТАТУС    {status}\n"
                "ДОБАВЛЕН  {added_at}\n"
                "━━━━━━━━━━━━━━━━━━</pre>"
            ),
            Button(Const("✅ Одобрить"), id="ch_approve", on_click=on_channel_approve_btn, when="is_pending"),
            Row(
                Button(Const("🔕 Отключить"), id="ch_disable", on_click=on_channel_disable, when="is_approved"),
                Button(Const("🔔 Включить"), id="ch_enable", on_click=on_channel_enable, when="is_disabled"),
            ),
            Button(Const("📅 Отправить расписание"), id="ch_schedule", on_click=on_channel_schedule, when="is_approved"),
            Button(Const("🗑 Удалить"), id="ch_delete", on_click=on_channel_delete),
            SwitchTo(Const("⬅️ Назад"), id="back_to_channels", state=AdminPanelSG.channels_list),
            state=AdminPanelSG.channel_detail,
            getter=get_channel_detail_data,
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
            SwitchTo(Const("✏️ Изменить алиас"), id="edit_alias", state=AdminPanelSG.group_alias_edit, when="is_creator"),
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
            Format(
                "✏️ <b>АЛИАС · ГРУППА {group_id}</b>\n"
                "<pre>━━━━━━━━━━━━━━━━━━\n"
                "ТЕКУЩИЙ   {alias}\n"
                "━━━━━━━━━━━━━━━━━━</pre>\n"
                "Пришлите новый алиас:"
            ),
            MessageInput(on_edit_group_alias_input, content_types=["text"]),
            Button(Const("🗑 Убрать алиас"), id="clear_alias", on_click=on_group_alias_clear),
            SwitchTo(Const("⬅️ Назад"), id="back_group_detail_alias", state=AdminPanelSG.group_detail),
            state=AdminPanelSG.group_alias_edit,
            getter=get_group_detail_data,
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
                "docs.google.com/spreadsheets/d/&lt;ID&gt;/edit"
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
            SwitchTo(Const("⬅️ Назад"), id="back_sheets_settings", state=AdminPanelSG.main),
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
        Window(
            Format(
                "📅 <b>АКТУАЛЬНОЕ РАСПИСАНИЕ</b>\n"
                "<pre>━━━━━━━━━━━━━━━━━━\n"
                "ДЕНЬ     {schedule_date}\n"
                "ГРУПП    {groups}\n"
                "ПАР      {lessons}\n"
                "━━━━━━━━━━━━━━━━━━</pre>\n"
                "Выберите группу для просмотра:"
            ),
            ScrollingGroup(
                Select(
                    Format("{item[0]}"),
                    id="schedule_group_select",
                    item_id_getter=lambda x: x[1],
                    items="schedule_groups",
                    on_click=on_schedule_group_selected,
                ),
                id="schedule_groups_scroll",
                width=2,
                height=5,
                hide_on_single_page=True,
                when="has_schedule",
            ),
            SwitchTo(Const("⬅️ Назад"), id="back_main_sched", state=AdminPanelSG.main),
            state=AdminPanelSG.schedule_view,
            getter=get_schedule_view_data,
        ),
    )
