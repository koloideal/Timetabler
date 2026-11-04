from datetime import date
from typing import cast

from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.api.entities import ChatEvent
from aiogram_dialog.widgets.kbd import (
    Button,
    ManagedMultiselect,
    Multiselect,
    Row,
    ScrollingGroup,
    SwitchTo,
)
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from timetabler.application.services.broadcast import BroadcastService
from timetabler.application.services.group_chat import GroupChatService
from timetabler.application.services.poller import next_study_day
from timetabler.application.services.study_group import StudyGroupService
from timetabler.application.services.user import UserService
from timetabler.infrastructure.config.app import AppConfig
from timetabler.presentation.messages import group_messages
from timetabler.presentation.telegram import TelegramNotifier
from timetabler.presentation.user_dialogs.group_setup import (
    GroupSetupSG,
    manageable_chats,
)


class UserMenuSG(StatesGroup):
    main = State()
    groups = State()


@inject
async def get_user_menu_data(
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    study_group_service: FromDishka[StudyGroupService],
    **kwargs: object,
) -> dict[str, object]:
    event_from_user = dialog_manager.middleware_data.get("event_from_user")
    user = await user_service.get_by_id(event_from_user.id) if event_from_user else None
    subscribed = set(user.groups) if user else set()
    aliases = {
        str(g.group_id): g.alias
        for g in await study_group_service.list_groups()
    }
    labels = [
        f"{g} — {aliases[g]}" if aliases.get(g) else g
        for g in sorted(subscribed, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x))
    ]
    enabled = user.notifications_enabled if user else True
    return {
        "subscribed_groups": ", ".join(labels) or "—",
        "notifications_btn": (
            "🔕 Выключить уведомления" if enabled else "🔔 Включить уведомления"
        ),
    }


@inject
async def on_toggle_notifications(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    user_service: FromDishka[UserService],
) -> None:
    user = await user_service.get_by_id(call.from_user.id)
    enabled = not (user.notifications_enabled if user else True)
    await user_service.set_notifications(call.from_user.id, enabled)
    await call.answer(
        "🔔 Уведомления включены" if enabled else "🔕 Уведомления выключены"
    )


async def _show_schedule(
    call: CallbackQuery,
    for_date: date,
    user_service: UserService,
    broadcast_service: BroadcastService,
    notifier: TelegramNotifier,
    app_config: AppConfig,
) -> None:
    user = await user_service.get_by_id(call.from_user.id)
    if user is None or not user.groups:
        await call.answer("❌ Сначала выберите группы в подписках", show_alert=True)
        return
    day = await broadcast_service.day_schedule(for_date)
    messages = group_messages(day, for_date, user.groups, app_config)
    if not messages:
        await call.answer("❌ Нет расписания за этот день", show_alert=True)
        return
    for markdown, markup in messages:
        await notifier.send_rich_message(call.from_user.id, markdown, markup)
    await call.answer()


@inject
async def on_show_today(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    user_service: FromDishka[UserService],
    broadcast_service: FromDishka[BroadcastService],
    notifier: FromDishka[TelegramNotifier],
    app_config: FromDishka[AppConfig],
) -> None:
    await _show_schedule(
        call, date.today(), user_service, broadcast_service, notifier, app_config
    )


@inject
async def on_show_tomorrow(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    user_service: FromDishka[UserService],
    broadcast_service: FromDishka[BroadcastService],
    notifier: FromDishka[TelegramNotifier],
    app_config: FromDishka[AppConfig],
) -> None:
    await _show_schedule(
        call, next_study_day(date.today()),
        user_service, broadcast_service, notifier, app_config,
    )


@inject
async def on_my_chats(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    group_chat_service: FromDishka[GroupChatService],
) -> None:
    if call.bot is None:
        return
    chats = await manageable_chats(call.bot, group_chat_service, call.from_user.id)
    if len(chats) == 1:
        chat = chats[0]
        state = (
            GroupSetupSG.settings
            if chat.study_groups
            else GroupSetupSG.pick_groups
        )
        await manager.start(state, data={"chat_id": chat.chat_id})
    else:
        await manager.start(GroupSetupSG.chats_list)


@inject
async def get_user_groups_data(
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    study_group_service: FromDishka[StudyGroupService],
    **kwargs: object,
) -> dict[str, object]:
    event_from_user = dialog_manager.middleware_data.get("event_from_user")
    user = await user_service.get_by_id(event_from_user.id) if event_from_user else None
    subscribed = set(user.groups) if user else set()

    widget = cast(
        ManagedMultiselect[str], dialog_manager.find("groups_ms")
    )
    groups = await study_group_service.list_groups()
    widget.widget.set_widget_data(
        dialog_manager,
        [str(g.group_id) for g in groups if str(g.group_id) in subscribed],
    )

    return {
        "groups": [(str(g.group_id), str(g.group_id)) for g in groups],
    }


@inject
async def on_group_toggled(
    event: ChatEvent,
    widget: ManagedMultiselect[str],
    manager: DialogManager,
    item_id: str,
    user_service: FromDishka[UserService],
) -> None:
    checked = widget.is_checked(item_id)
    event_from_user = manager.middleware_data.get("event_from_user")
    if event_from_user is None:
        return
    await user_service.set_group_membership(event_from_user.id, int(item_id), checked)


def build_user_menu_dialog() -> Dialog:
    return Dialog(
        Window(
            Format(
                "<b>📅 Timetabler</b>\n\n"
                "🎓 <b>Вы подписаны:</b> {subscribed_groups}\n\n"
                "<i>powered by <b>kolo</b></i>"
            ),
            Row(
                Button(Const("📅 Сегодня"), id="u_sched_today", on_click=on_show_today),
                Button(Const("📅 Завтра"), id="u_sched_tomorrow", on_click=on_show_tomorrow),
            ),
            Button(Format("{notifications_btn}"), id="u_notify", on_click=on_toggle_notifications),
            Row(
                SwitchTo(Const("🎓 Подписки"), id="u_groups", state=UserMenuSG.groups),
                Button(Const("💬 Мои чаты"), id="u_chats", on_click=on_my_chats),
            ),
            state=UserMenuSG.main,
            getter=get_user_menu_data,
        ),
        Window(
            Const(
                "<b>🎓 Подписки</b>\n\n"
                "Выберите группы, по которым присылать расписание:"
            ),
            ScrollingGroup(
                Multiselect(
                    Format("✅ {item[0]}"),
                    Format("⬜ {item[0]}"),
                    id="groups_ms",
                    item_id_getter=lambda x: x[1],
                    items="groups",
                    type_factory=str,
                    on_state_changed=on_group_toggled,
                ),
                id="groups_scroll",
                width=3,
                height=7,
                hide_on_single_page=True,
            ),
            SwitchTo(Const("◀️ Назад"), id="u_groups_back", state=UserMenuSG.main),
            state=UserMenuSG.groups,
            getter=get_user_groups_data,
        ),
    )
