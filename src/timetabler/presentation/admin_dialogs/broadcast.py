from datetime import datetime, timezone
from typing import Any, cast

from aiogram import F
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
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

from timetabler.application.services.audience import (
    MODE_ALL,
    MODE_COURSES,
    MODE_GROUPS,
    MODE_SPECIALTIES,
    Audience,
    AudienceService,
    AudienceSpec,
)
from timetabler.application.services.mass_broadcast import (
    BroadcastJob,
    MassBroadcastService,
)
from timetabler.infrastructure.config.models import Config

_MODE_TITLES = {
    MODE_ALL: "🌐 Все",
    MODE_COURSES: "📚 По курсам",
    MODE_SPECIALTIES: "🎓 По специальностям",
    MODE_GROUPS: "👥 По группам",
}
_PICK_HINTS = {
    MODE_COURSES: "Выберите курсы:",
    MODE_SPECIALTIES: "Выберите специальности:",
    MODE_GROUPS: "Выберите группы:",
}


def _spec(manager: DialogManager) -> AudienceSpec:
    data = manager.dialog_data
    return AudienceSpec(
        mode=data.get("bc_mode", MODE_ALL),
        values=list(data.get("bc_values", [])),
        include_chats=bool(data.get("bc_chats", True)),
    )


async def _label(spec: AudienceSpec, audience_service: AudienceService) -> str:
    chats = "с чатами" if spec.include_chats else "без чатов"
    if spec.mode == MODE_ALL:
        return f"все ({chats})"
    names = dict((v, n) for n, v in await audience_service.options(spec.mode))
    picked = ", ".join(
        v if spec.mode == MODE_GROUPS else names.get(v, v) for v in spec.values
    )
    kind = {MODE_COURSES: "курсы", MODE_SPECIALTIES: "специальности", MODE_GROUPS: "группы"}[spec.mode]
    return f"{kind}: {picked} ({chats})"


def _is_creator(manager: DialogManager, config: Config) -> bool:
    user = manager.middleware_data.get("event_from_user")
    return bool(user and user.id == config.bot.creator_id)


def _job_text(job: BroadcastJob) -> str:
    end = job.finished_at or datetime.now(timezone.utc)
    seconds = int((end - job.started_at).total_seconds())
    pct = int(job.done / job.total * 100) if job.total else 100
    bar = "▓" * (pct // 10) + "░" * (10 - pct // 10)
    state = (
        "🟢 идёт" if job.running
        else "⛔ остановлена" if job.cancelled
        else "✅ завершена"
    )
    lines = [
        f"<b>📣 Рассылка #{job.id}</b> · {state}",
        f"<b>Аудитория:</b> {job.label}",
        f"{bar} {pct}% ({job.done}/{job.total})",
        f"✅ {job.sent}  🚫 {job.blocked}  ❌ {job.failed}",
        f"⏱ {seconds} с",
    ]
    return "\n".join(lines)


def build_broadcast_windows(sg: Any) -> list[Window]:
    def mode_handler(mode: str):
        async def handler(
            call: CallbackQuery, button: Button, manager: DialogManager
        ) -> None:
            manager.dialog_data["bc_mode"] = mode
            manager.dialog_data["bc_values"] = []
            if mode == MODE_ALL:
                await manager.switch_to(sg.bc_compose)
                return
            await cast(ManagedMultiselect, manager.find("bc_pick_ms")).reset_checked()
            await manager.switch_to(sg.bc_pick)

        return handler

    async def on_toggle_chats(
        call: CallbackQuery, button: Button, manager: DialogManager
    ) -> None:
        manager.dialog_data["bc_chats"] = not manager.dialog_data.get("bc_chats", True)

    @inject
    async def get_menu_data(
        dialog_manager: DialogManager,
        mass_service: FromDishka[MassBroadcastService],
        **kwargs: object,
    ) -> dict[str, object]:
        include = bool(dialog_manager.dialog_data.get("bc_chats", True))
        job = mass_service.latest()
        return {
            "chats_btn": "💬 Групповые чаты: ✅ вкл" if include else "💬 Групповые чаты: ⬜ выкл",
            "has_job": job is not None,
            "job_btn": (
                f"📊 Рассылка #{job.id}: {job.done}/{job.total}" if job else ""
            ),
        }

    @inject
    async def get_pick_data(
        dialog_manager: DialogManager,
        audience_service: FromDishka[AudienceService],
        **kwargs: object,
    ) -> dict[str, object]:
        mode = dialog_manager.dialog_data.get("bc_mode", MODE_GROUPS)
        options = await audience_service.options(mode)
        return {
            "pick_hint": _PICK_HINTS.get(mode, "Выберите:"),
            "options": options,
            "has_options": bool(options),
        }

    async def on_pick_next(
        call: CallbackQuery, button: Button, manager: DialogManager
    ) -> None:
        ms = cast(ManagedMultiselect, manager.find("bc_pick_ms"))
        checked = [str(v) for v in ms.get_checked()]
        if not checked:
            await call.answer("❌ Выберите хотя бы один пункт", show_alert=True)
            return
        manager.dialog_data["bc_values"] = checked
        await manager.switch_to(sg.bc_compose)

    @inject
    async def get_audience_data(
        dialog_manager: DialogManager,
        audience_service: FromDishka[AudienceService],
        **kwargs: object,
    ) -> dict[str, object]:
        spec = _spec(dialog_manager)
        audience = await audience_service.resolve(spec)
        return {
            "audience": await _label(spec, audience_service),
            "users": len(audience.user_ids),
            "chats": len(audience.chat_ids),
            "can_start": audience.total > 0,
        }

    @inject
    async def on_compose(
        message: Message,
        widget: MessageInput,
        manager: DialogManager,
        config: FromDishka[Config],
    ) -> None:
        if not _is_creator(manager, config):
            return
        if message.media_group_id:
            if manager.dialog_data.get("bc_album") != message.media_group_id:
                manager.dialog_data["bc_album"] = message.media_group_id
                await message.answer(
                    "❌ Альбомы не поддерживаются — пришлите одно сообщение "
                    "(для нескольких фото используйте отдельные рассылки)."
                )
            return
        manager.dialog_data["bc_src_chat"] = message.chat.id
        manager.dialog_data["bc_src_msg"] = message.message_id
        await manager.switch_to(sg.bc_confirm)

    @inject
    async def on_start(
        call: CallbackQuery,
        button: Button,
        manager: DialogManager,
        config: FromDishka[Config],
        audience_service: FromDishka[AudienceService],
        mass_service: FromDishka[MassBroadcastService],
    ) -> None:
        if not _is_creator(manager, config):
            return
        data = manager.dialog_data
        if "bc_src_msg" not in data:
            await call.answer("❌ Сначала пришлите сообщение", show_alert=True)
            await manager.switch_to(sg.bc_compose)
            return
        if mass_service.active() is not None:
            await call.answer("⏳ Уже идёт другая рассылка", show_alert=True)
            return
        spec = _spec(manager)
        audience: Audience = await audience_service.resolve(spec)
        if audience.total == 0:
            await call.answer("❌ Нет получателей", show_alert=True)
            return
        job = mass_service.start(
            audience, data["bc_src_chat"], data["bc_src_msg"],
            await _label(spec, audience_service),
        )
        data["bc_job_id"] = job.id
        await call.answer("🚀 Рассылка запущена")
        await manager.switch_to(sg.bc_status)

    @inject
    async def get_status_data(
        dialog_manager: DialogManager,
        mass_service: FromDishka[MassBroadcastService],
        **kwargs: object,
    ) -> dict[str, object]:
        job_id = dialog_manager.dialog_data.get("bc_job_id")
        job = mass_service.get(job_id) if job_id else None
        job = job or mass_service.latest()
        if job is None:
            return {"status_text": "Рассылок ещё не было", "can_stop": False}
        return {"status_text": _job_text(job), "can_stop": job.running}

    @inject
    async def on_stop(
        call: CallbackQuery,
        button: Button,
        manager: DialogManager,
        mass_service: FromDishka[MassBroadcastService],
    ) -> None:
        job = mass_service.latest()
        if job is not None and mass_service.cancel(job.id):
            await call.answer("⛔ Останавливаю…")
        else:
            await call.answer("Рассылка уже завершена")

    async def on_status_open(
        call: CallbackQuery, button: Button, manager: DialogManager
    ) -> None:
        manager.dialog_data.pop("bc_job_id", None)
        await manager.switch_to(sg.bc_status)

    async def on_refresh(
        call: CallbackQuery, button: Button, manager: DialogManager
    ) -> None:
        await call.answer("🔄")

    return [
        Window(
            Const(
                "<b>📣 Рассылка</b>\n\n"
                "Выберите аудиторию — бот скопирует ваше сообщение "
                "(любого типа) в личку и групповые чаты. Каналы не затрагиваются."
            ),
            Row(
                Button(Const(_MODE_TITLES[MODE_ALL]), id="bc_all", on_click=mode_handler(MODE_ALL)),
                Button(Const(_MODE_TITLES[MODE_COURSES]), id="bc_courses", on_click=mode_handler(MODE_COURSES)),
            ),
            Row(
                Button(Const(_MODE_TITLES[MODE_SPECIALTIES]), id="bc_specs", on_click=mode_handler(MODE_SPECIALTIES)),
                Button(Const(_MODE_TITLES[MODE_GROUPS]), id="bc_groups", on_click=mode_handler(MODE_GROUPS)),
            ),
            Button(Format("{chats_btn}"), id="bc_chats", on_click=on_toggle_chats),
            Button(Format("{job_btn}"), id="bc_job", on_click=on_status_open, when=F["has_job"]),
            SwitchTo(Const("◀️ Назад"), id="bc_back_main", state=sg.main),
            state=sg.bc_menu,
            getter=get_menu_data,
        ),
        Window(
            Format("<b>📣 Рассылка</b>\n\n{pick_hint}", when=F["has_options"]),
            Const("<b>📣 Рассылка</b>\n\nПока нет данных для выбора.", when=~F["has_options"]),
            ScrollingGroup(
                Multiselect(
                    Format("✅ {item[0]}"),
                    Format("⬜ {item[0]}"),
                    id="bc_pick_ms",
                    item_id_getter=lambda x: x[1],
                    items="options",
                    type_factory=str,
                ),
                id="bc_pick_scroll",
                width=3,
                height=8,
                hide_on_single_page=True,
            ),
            Row(
                Button(Const("➡️ Далее"), id="bc_pick_next", on_click=on_pick_next, when=F["has_options"]),
                SwitchTo(Const("◀️ Назад"), id="bc_pick_back", state=sg.bc_menu),
            ),
            state=sg.bc_pick,
            getter=get_pick_data,
        ),
        Window(
            Format(
                "<b>📣 Рассылка</b>\n\n"
                "<b>Аудитория:</b> {audience}\n"
                "<b>Получатели:</b> 👤 {users} · 💬 {chats}\n\n"
                "✍️ <b>Пришлите сообщение для рассылки</b> — текст, фото, видео, "
                "файл, стикер, голосовое. Оно уйдёт как есть.\n"
                "<i>Не удаляйте его до конца рассылки. Альбомы не поддерживаются.</i>"
            ),
            MessageInput(on_compose),
            SwitchTo(Const("◀️ Назад"), id="bc_compose_back", state=sg.bc_menu),
            state=sg.bc_compose,
            getter=get_audience_data,
        ),
        Window(
            Format(
                "<b>📣 Подтверждение</b>\n\n"
                "<b>Аудитория:</b> {audience}\n"
                "<b>Получатели:</b> 👤 {users} · 💬 {chats}\n\n"
                "Ваше сообщение выше будет скопировано получателям. Запустить?"
            ),
            Button(Const("🚀 Запустить"), id="bc_start", on_click=on_start, when=F["can_start"]),
            Row(
                SwitchTo(Const("✏️ Другое сообщение"), id="bc_redo", state=sg.bc_compose),
                SwitchTo(Const("❌ Отмена"), id="bc_cancel", state=sg.bc_menu),
            ),
            state=sg.bc_confirm,
            getter=get_audience_data,
        ),
        Window(
            Format("{status_text}"),
            Row(
                Button(Const("🔄 Обновить"), id="bc_refresh", on_click=on_refresh),
                Button(Const("⛔ Остановить"), id="bc_stop", on_click=on_stop, when=F["can_stop"]),
            ),
            SwitchTo(Const("◀️ В админку"), id="bc_status_back", state=sg.main),
            state=sg.bc_status,
            getter=get_status_data,
        ),
    ]
