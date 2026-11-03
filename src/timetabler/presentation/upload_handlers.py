import logging
from datetime import date
from io import BytesIO

from aiogram import F, Router
from aiogram.enums.chat_type import ChatType
from aiogram.types import CallbackQuery, Message
from dishka import FromDishka

from timetabler.application.exceptions import TimetableParseError
from timetabler.application.services.bot import BotService
from timetabler.application.services.broadcast import BroadcastService
from timetabler.application.services.timetable import TimetableService
from timetabler.application.services.user import UserService
from timetabler.infrastructure.config.app import AppConfig
from timetabler.infrastructure.config.models import Config

logger = logging.getLogger(__name__)

upload_router = Router()
upload_router.message.filter(F.chat.type == ChatType.PRIVATE)


@upload_router.message(F.document)
async def upload_timetable(
    message: Message,
    timetable_service: FromDishka[TimetableService],
    user_service: FromDishka[UserService],
    bot_service: FromDishka[BotService],
    app_config: FromDishka[AppConfig],
) -> None:
    document = message.document
    assert document is not None
    filename = document.file_name or ""

    if not filename.lower().endswith(app_config.supported_extensions):
        await message.answer(app_config.format_hint)
        return

    assert message.from_user is not None
    uploader, _ = await user_service.get_or_create(message.from_user.id, message.from_user.username)

    buffer = BytesIO()
    assert message.bot is not None
    await message.bot.download(document, destination=buffer)

    try:
        result = await timetable_service.import_document(filename, buffer.getvalue(), message.from_user.id)
    except TimetableParseError as e:
        await message.answer(
            f"❌ <b>НЕ РАЗОБРАНО</b>\n<pre>{e}</pre>"
        )
        await bot_service.notify_creator_upload_failed(uploader, filename, str(e))
        return

    dates = ", ".join(d.strftime("%d.%m.%Y") for d in result.dates)
    await message.answer(
        "✅ <b>РАЗОБРАНО</b>\n"
        f"<pre>ДАТЫ    {dates}\nПАР     {result.lessons}\nГРУПП   {result.groups}</pre>\n"
        "Отправлено создателю на подтверждение."
    )
    await bot_service.send_upload_review(uploader, filename, result)


@upload_router.callback_query(F.data.startswith("tt_ok:"))
async def confirm_broadcast(
    call: CallbackQuery,
    broadcast_service: FromDishka[BroadcastService],
    config: FromDishka[Config],
) -> None:
    if call.from_user.id != config.bot.creator_id:
        await call.answer("⛔ Только создатель", show_alert=True)
        return

    assert call.data is not None
    assert isinstance(call.message, Message)
    for_date = date.fromisoformat(call.data.split(":", 1)[1])
    report = await broadcast_service.broadcast(for_date)

    await call.message.edit_text(
        f"{call.message.html_text}\n\n"
        f"✅ <b>РАЗОСЛАНО</b>\n"
        f"<pre>ЮЗЕРАМ  {report.users_sent} (+{report.users_failed} недост.)"
        f"\nЧАТАМ    {report.chats_sent} (+{report.chats_failed} недост.)"
        f"\nГРУПП    {report.groups}</pre>"
    )
    await call.answer("✅ Разослано")


@upload_router.callback_query(F.data.startswith("tt_no:"))
async def decline_broadcast(call: CallbackQuery, config: FromDishka[Config]) -> None:
    if call.from_user.id != config.bot.creator_id:
        await call.answer("⛔ Только создатель", show_alert=True)
        return

    assert isinstance(call.message, Message)
    await call.message.edit_text(f"{call.message.html_text}\n\n❌ <b>ОТКЛОНЕНО</b>")
    await call.answer("Отклонено")
