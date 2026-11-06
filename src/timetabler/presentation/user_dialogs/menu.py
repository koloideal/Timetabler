from datetime import date, datetime
from typing import cast
from zoneinfo import ZoneInfo

from aiogram import F
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
from timetabler.application.services.lesson_timing import first_event, now_status
from timetabler.application.services.poller import next_study_day, schedule_today
from timetabler.application.services.study_group import StudyGroupService
from timetabler.application.services.user import UserService
from timetabler.domain.schemas import DaySchedule, ResolvedLesson, User
from timetabler.infrastructure.config.app import AppConfig
from timetabler.presentation.messages import (
    group_messages,
    note_blocks,
    now_status_text,
)
from timetabler.presentation.telegram import TelegramNotifier, TelegramScheduleSender
from timetabler.presentation.user_dialogs.group_setup import (
    GroupSetupSG,
    manageable_chats,
)


class UserMenuSG(StatesGroup):
    main = State()
    groups = State()


def _user_lessons(day: DaySchedule, user: User) -> list[ResolvedLesson]:
    group_ids = {int(g) for g in user.groups if g.isdigit()}
    sub = int(user.subgroup_mode) if user.subgroup_mode in ("1", "2") else None
    return [
        l
        for gid in group_ids
        for l in day.by_group.get(gid, ())
        if sub is None or l.subgroup in (None, sub)
    ]


async def _now_info(
    user: User | None,
    broadcast_service: BroadcastService,
    app_config: AppConfig,
) -> str:
    if user is None or not user.groups:
        return ""
    tz = ZoneInfo(app_config.revisions.update_timezone)
    now = datetime.now(tz)
    day = await broadcast_service.day_schedule(now.date())
    now_sec = now.hour * 3600 + now.minute * 60 + now.second
    status = now_status(_user_lessons(day, user), now_sec)
    tomorrow_first = None
    if status.kind in {"done", "empty"}:
        tomorrow = await broadcast_service.day_schedule(next_study_day(now.date()))
        tomorrow_first = first_event(_user_lessons(tomorrow, user))
    return now_status_text(status, tomorrow_first)


@inject
async def get_user_menu_data(
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    study_group_service: FromDishka[StudyGroupService],
    broadcast_service: FromDishka[BroadcastService],
    app_config: FromDishka[AppConfig],
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
    pin_enabled = user.pin_enabled if user else False
    now_info = await _now_info(user, broadcast_service, app_config)
    return {
        "subscribed_groups": ", ".join(labels) or "—",
        "notifications_btn": (
            "🔕 Выключить уведомления" if enabled else "🔔 Включить уведомления"
        ),
        "pin_btn": (
            "📌 Откреплять расписание" if pin_enabled else "📌 Закреплять расписание"
        ),
        "now_info": now_info,
        "has_now_info": bool(now_info),
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


@inject
async def on_toggle_dm_pin(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    user_service: FromDishka[UserService],
    schedule_sender: FromDishka[TelegramScheduleSender],
) -> None:
    user = await user_service.get_by_id(call.from_user.id)
    enabled = not (user.pin_enabled if user else False)
    await user_service.set_pin(call.from_user.id, enabled)
    if not enabled and user and user.pinned_message_ids:
        for mid in user.pinned_message_ids:
            await schedule_sender.unpin_chat_message(call.from_user.id, mid)
        await user_service.set_pinned_messages(call.from_user.id, [])
    await call.answer("📌 Закреп включён" if enabled else "📌 Закреп выключен")


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
    messages = group_messages(
        day, for_date, user.groups, app_config,
        mode=user.subgroup_mode, is_compact=True,
    )
    if not messages:
        await call.answer("❌ Нет расписания за этот день", show_alert=True)
        return
    for blocks, markup in messages:
        if day.updated_label:
            blocks = blocks + note_blocks(day.updated_label)
        await notifier.send_rich_message(call.from_user.id, blocks, markup)
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
        call, schedule_today(app_config.revisions.update_timezone),
        user_service, broadcast_service, notifier, app_config,
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
        call, next_study_day(schedule_today(app_config.revisions.update_timezone)),
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
        "has_groups": bool(groups),
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
                "🎓 <b>Вы подписаны:</b> {subscribed_groups}"
            ),
            Format("\n\n{now_info}", when=F["has_now_info"]),
            Const("\n\n<i>powered by <b>kolo</b></i>"),
            Row(
                Button(Const("📅 Сегодня"), id="u_sched_today", on_click=on_show_today),
                Button(Const("📅 Завтра"), id="u_sched_tomorrow", on_click=on_show_tomorrow),
            ),
            Button(Format("{notifications_btn}"), id="u_notify", on_click=on_toggle_notifications),
            Button(Format("{pin_btn}"), id="u_pin", on_click=on_toggle_dm_pin),
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
                "Выберите группы, по которым присылать расписание:",
                when=F["has_groups"],
            ),
            Const(
                "<b>🎓 Подписки</b>\n\n"
                "Расписание ещё не загружено — групп нет. Попробуйте позже.",
                when=~F["has_groups"],
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
                when=F["has_groups"],
            ),
            SwitchTo(Const("◀️ Назад"), id="u_groups_back", state=UserMenuSG.main),
            state=UserMenuSG.groups,
            getter=get_user_groups_data,
        ),
    )
