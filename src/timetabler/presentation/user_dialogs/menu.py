from datetime import date, datetime, timedelta
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
    Select,
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
    pick_main = State()
    groups = State()


def _onboarding(dialog_manager: DialogManager) -> bool:
    start_data = dialog_manager.start_data
    return bool(
        isinstance(start_data, dict) and start_data.get("onboarding")
    ) and not dialog_manager.dialog_data.get("onboarding_done")


def _user_lessons(day: DaySchedule, user: User) -> list[ResolvedLesson]:
    sub = int(user.subgroup_mode) if user.subgroup_mode in ("1", "2") else None
    if user.main_group is not None:
        candidates: list[ResolvedLesson] = day.by_group.get(user.main_group, [])
    else:
        group_ids = {int(g) for g in user.groups if g.isdigit()}
        candidates = [l for gid in group_ids for l in day.by_group.get(gid, ())]
    return [l for l in candidates if sub is None or l.subgroup in (None, sub)]


async def _now_info(
    user: User | None,
    broadcast_service: BroadcastService,
    app_config: AppConfig,
) -> str:
    if user is None or (not user.groups and user.main_group is None):
        return ""
    tz = ZoneInfo(app_config.revisions.update_timezone)
    now = datetime.now(tz)
    day = await broadcast_service.day_schedule(now.date())
    now_sec = now.hour * 3600 + now.minute * 60 + now.second
    status = now_status(_user_lessons(day, user), now_sec)
    next_first = None
    next_label = "завтра"
    if status.kind in {"done", "empty"}:
        next_date = next_study_day(now.date())
        next_day = await broadcast_service.day_schedule(next_date)
        next_first = first_event(_user_lessons(next_day, user))
        if next_date != now.date() + timedelta(days=1):
            next_label = (
                f"{app_config.weekdays_full[next_date.weekday()]} "
                f"{next_date.strftime('%d.%m')}"
            )
    return now_status_text(status, next_first, next_label)


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
    main = str(user.main_group) if user and user.main_group is not None else None
    subscribed = {
        g for g in (user.groups if user else ()) if g != main
    }
    aliases = {
        str(g.group_id): g.alias
        for g in await study_group_service.list_groups()
    }
    labels = [
        f"{g} — <i>{aliases[g]}</i>" if aliases.get(g) else g
        for g in sorted(subscribed, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else x))
    ]
    main_label = (
        f"{main} — <i>{aliases[main]}</i>" if main and aliases.get(main)
        else main or "не выбрана"
    )
    enabled = user.notifications_enabled if user else True
    pin_enabled = user.pin_enabled if user else False
    now_info = await _now_info(user, broadcast_service, app_config)
    today = schedule_today(app_config.revisions.update_timezone)
    next_date = next_study_day(today)
    return {
        "main_group_label": main_label,
        "watched_block": (
            f"\n\n👀 <b>Наблюдаю:</b> {', '.join(labels)}" if labels else ""
        ),
        "tomorrow_btn": (
            "📅 Завтра" if next_date == today + timedelta(days=1)
            else "📅 Послезавтра"
        ),
        "notifications_btn": (
            "✅ Уведомления 🔔" if enabled else "❌ Уведомления 🔔"
        ),
        "pin_btn": "✅ Закреп 📌" if pin_enabled else "❌ Закреп 📌",
        "now_block": f"\n\n{now_info.replace(chr(10), chr(10) * 2)}" if now_info else "",
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
    if user is None or (not user.groups and user.main_group is None):
        await call.answer("❌ Сначала выберите группы в подписках", show_alert=True)
        return
    groups = list(user.groups)
    if user.main_group is not None:
        groups = [str(user.main_group)] + [
            g for g in groups if g != str(user.main_group)
        ]
    day = await broadcast_service.day_schedule(for_date)
    messages = group_messages(
        day, for_date, groups, app_config,
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
async def get_pick_main_data(
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    study_group_service: FromDishka[StudyGroupService],
    **kwargs: object,
) -> dict[str, object]:
    event_from_user = dialog_manager.middleware_data.get("event_from_user")
    user = await user_service.get_by_id(event_from_user.id) if event_from_user else None
    groups = await study_group_service.list_groups()
    onboarding = _onboarding(dialog_manager)
    return {
        "groups": [(g.group_id, str(g.group_id)) for g in groups],
        "has_groups": bool(groups),
        "has_main": (
            dialog_manager.dialog_data.get("pending_main") is not None
            if onboarding
            else user is not None and user.main_group is not None
        ),
        "onboarding": onboarding,
    }


@inject
async def on_main_group_picked(
    call: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
    user_service: FromDishka[UserService],
) -> None:
    if _onboarding(manager):
        manager.dialog_data["pending_main"] = int(item_id)
    else:
        await user_service.set_main_group(call.from_user.id, int(item_id))
    await call.answer(f"⭐ Ваша группа — {item_id}")
    await manager.switch_to(UserMenuSG.groups)


@inject
async def on_main_group_cleared(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    user_service: FromDishka[UserService],
) -> None:
    if _onboarding(manager):
        manager.dialog_data.pop("pending_main", None)
    else:
        await user_service.set_main_group(call.from_user.id, None)
    await call.answer("⭐ Своя группа убрана")
    await manager.switch_to(UserMenuSG.groups)


@inject
async def get_user_groups_data(
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    study_group_service: FromDishka[StudyGroupService],
    **kwargs: object,
) -> dict[str, object]:
    event_from_user = dialog_manager.middleware_data.get("event_from_user")
    user = await user_service.get_by_id(event_from_user.id) if event_from_user else None
    onboarding = _onboarding(dialog_manager)
    if onboarding:
        pending_main = dialog_manager.dialog_data.get("pending_main")
        main = str(pending_main) if pending_main is not None else None
        subscribed = set(dialog_manager.dialog_data.get("pending_groups", ()))
    else:
        main = str(user.main_group) if user and user.main_group is not None else None
        subscribed = set(user.groups) if user else set()

    groups = await study_group_service.list_groups()
    items = [g for g in groups if str(g.group_id) != main]
    widget = cast(
        ManagedMultiselect[str], dialog_manager.find("groups_ms")
    )
    widget.widget.set_widget_data(
        dialog_manager,
        [str(g.group_id) for g in items if str(g.group_id) in subscribed],
    )

    return {
        "groups": [(str(g.group_id), str(g.group_id)) for g in items],
        "has_groups": bool(groups),
        "main_btn": (
            f"⭐ Моя группа: {main}" if main else "⭐ Выбрать свою группу"
        ),
        "onboarding": onboarding,
    }


@inject
async def on_group_toggled(
    event: ChatEvent,
    widget: ManagedMultiselect[str],
    manager: DialogManager,
    item_id: str,
    user_service: FromDishka[UserService],
    broadcast_service: FromDishka[BroadcastService],
) -> None:
    checked = widget.is_checked(item_id)
    if _onboarding(manager):
        pending = set(manager.dialog_data.get("pending_groups", ()))
        pending.discard(item_id)
        if checked:
            pending.add(item_id)
        manager.dialog_data["pending_groups"] = sorted(pending)
        return
    event_from_user = manager.middleware_data.get("event_from_user")
    if event_from_user is None:
        return
    await user_service.set_group_membership(event_from_user.id, int(item_id), checked)
    if not checked:
        await broadcast_service.drop_user_group_messages(
            event_from_user.id, int(item_id)
        )


@inject
async def on_pick_main_done(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    study_group_service: FromDishka[StudyGroupService],
) -> None:
    if _onboarding(manager) and (
        manager.dialog_data.get("pending_main") is None
        and await study_group_service.list_groups()
    ):
        await call.answer(
            "⭐ Сначала выберите свою группу", show_alert=True
        )
        return
    await manager.switch_to(UserMenuSG.groups)


@inject
async def on_groups_done(
    call: CallbackQuery,
    button: Button,
    manager: DialogManager,
    user_service: FromDishka[UserService],
    study_group_service: FromDishka[StudyGroupService],
    notifier: FromDishka[TelegramNotifier],
) -> None:
    if _onboarding(manager):
        pending_main = manager.dialog_data.get("pending_main")
        if pending_main is None and await study_group_service.list_groups():
            await call.answer(
                "⭐ Сначала выберите свою группу", show_alert=True
            )
            await manager.switch_to(UserMenuSG.pick_main)
            return
        user = await user_service.complete_onboarding(
            call.from_user.id,
            call.from_user.username,
            main_group=pending_main,
            groups=manager.dialog_data.get("pending_groups", []),
        )
        if user is not None:
            await notifier.notify_new_user(user)
    manager.dialog_data["onboarding_done"] = True
    await manager.switch_to(UserMenuSG.main)


def build_user_menu_dialog() -> Dialog:
    return Dialog(
        Window(
            Format(
                "<b>📅 Timetabler</b>\n\n\n"
                "⭐ <b>Моя группа:</b> {main_group_label}"
                "{watched_block}"
                "{now_block}"
            ),
            Const("\n\n<i>powered by <b>kolo</b></i>"),
            Row(
                Button(Const("📅 Сегодня"), id="u_sched_today", on_click=on_show_today),
                Button(Format("{tomorrow_btn}"), id="u_sched_tomorrow", on_click=on_show_tomorrow),
            ),
            Button(Format("{pin_btn}"), id="u_pin", on_click=on_toggle_dm_pin),
            Row(
                SwitchTo(Const("🎓 Подписки"), id="u_groups", state=UserMenuSG.groups),
                Button(Const("💬 Чаты"), id="u_chats", on_click=on_my_chats),
            ),
            Button(Format("{notifications_btn}"), id="u_notify", on_click=on_toggle_notifications),
            state=UserMenuSG.main,
            getter=get_user_menu_data,
        ),
        Window(
            Const(
                "<b>⭐ Моя группа</b>\n\n"
                "Выберите свою учебную группу — по ней считаются подсказки "
                "(какая пара идёт и что дальше):",
                when=F["has_groups"],
            ),
            Const(
                "<b>⭐ Моя группа</b>\n\n"
                "Расписание ещё не загружено — групп нет. Попробуйте позже.",
                when=~F["has_groups"],
            ),
            ScrollingGroup(
                Select(
                    Format("{item[1]}"),
                    id="main_group_sel",
                    item_id_getter=lambda x: str(x[0]),
                    items="groups",
                    on_click=on_main_group_picked,
                ),
                id="main_group_scroll",
                width=3,
                height=8,
                hide_on_single_page=True,
                when=F["has_groups"],
            ),
            Button(
                Const("✖️ Убрать мою группу"),
                id="main_group_clear",
                on_click=on_main_group_cleared,
                when=F["has_main"] & ~F["onboarding"],
            ),
            Button(
                Const("➡️ Далее"),
                id="main_next",
                on_click=on_pick_main_done,
                when=F["onboarding"],
            ),
            Button(
                Const("◀️ Назад"),
                id="main_back",
                on_click=on_pick_main_done,
                when=~F["onboarding"],
            ),
            state=UserMenuSG.pick_main,
            getter=get_pick_main_data,
        ),
        Window(
            Const(
                "<b>👀 Наблюдаемые группы</b>\n\n"
                "Отметьте дополнительные группы — по ним тоже будет "
                "приходить расписание:",
                when=F["has_groups"],
            ),
            Const(
                "<b>👀 Наблюдаемые группы</b>\n\n"
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
            SwitchTo(Format("{main_btn}"), id="u_pick_main", state=UserMenuSG.pick_main),
            Button(
                Const("▶️ Продолжить"),
                id="u_groups_continue",
                on_click=on_groups_done,
                when=F["onboarding"],
            ),
            Button(
                Const("◀️ Назад"),
                id="u_groups_back",
                on_click=on_groups_done,
                when=~F["onboarding"],
            ),
            state=UserMenuSG.groups,
            getter=get_user_groups_data,
        ),
    )
