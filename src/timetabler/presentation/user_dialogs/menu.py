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
    total = len(await study_group_service.list_groups())
    enabled = user.notifications_enabled if user else True
    return {
        "subscribed": len(subscribed),
        "total_groups": total,
        "notifications": "🔔 включены" if enabled else "🔕 выключены",
        "notifications_btn": "🔔 Уведомления" if enabled else "🔕 Уведомления",
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
    await call.answer("Уведомления включены" if enabled else "Уведомления выключены")


@inject
async def on_show_my_schedule(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    user_service: FromDishka[UserService],
    broadcast_service: FromDishka[BroadcastService],
    notifier: FromDishka[TelegramNotifier],
    app_config: FromDishka[AppConfig],
) -> None:
    user = await user_service.get_by_id(call.from_user.id)
    if user is None or not user.groups:
        await call.answer("Сначала выбери группы", show_alert=True)
        return
    target = next_study_day(date.today())
    day = await broadcast_service.day_schedule(target)
    messages = group_messages(day, target, user.groups, app_config)
    if not messages:
        await call.answer("Расписания пока нет", show_alert=True)
        return
    for markdown, markup in messages:
        await notifier.send_rich_message(call.from_user.id, markdown, markup)
    await call.answer()


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
                "📅 <b>Расписание занятий</b>\n\n"
                "Присылаю новое расписание, как только оно появляется.\n\n"
                "Подписка: {subscribed} из {total_groups} групп\n"
                "Уведомления: {notifications}"
            ),
            Button(Const("📅 Моё расписание"), id="u_schedule", on_click=on_show_my_schedule),
            SwitchTo(Const("📚 Подписки"), id="u_groups", state=UserMenuSG.groups),
            Button(Const("👥 Мои группы"), id="u_chats", on_click=on_my_chats),
            Button(Format("{notifications_btn}"), id="u_notify", on_click=on_toggle_notifications),
            state=UserMenuSG.main,
            getter=get_user_menu_data,
        ),
        Window(
            Const("Отметьте группы, по которым присылать расписание:"),
            ScrollingGroup(
                Multiselect(
                    Format("✅ {item[0]}"),
                    Format("{item[0]}"),
                    id="groups_ms",
                    item_id_getter=lambda x: x[1],
                    items="groups",
                    type_factory=str,
                    on_state_changed=on_group_toggled,
                ),
                id="groups_scroll",
                width=3,
                height=6,
                hide_on_single_page=True,
            ),
            SwitchTo(Const("Назад"), id="u_groups_back", state=UserMenuSG.main),
            state=UserMenuSG.groups,
            getter=get_user_groups_data,
        ),
    )
