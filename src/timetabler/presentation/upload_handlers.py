import logging
from io import BytesIO

from aiogram import F, Router
from aiogram.enums.chat_type import ChatType
from aiogram.types import Message
from dishka import FromDishka

from timetabler.application.exceptions import TimetableParseError
from timetabler.application.services.timetable import TimetableService
from timetabler.infrastructure.config.app import AppConfig

logger = logging.getLogger(__name__)

upload_router = Router()
upload_router.message.filter(F.chat.type == ChatType.PRIVATE)


@upload_router.message(F.document)
async def upload_timetable(
    message: Message,
    timetable_service: FromDishka[TimetableService],
    app_config: FromDishka[AppConfig],
) -> None:
    document = message.document
    assert document is not None
    filename = document.file_name or ""

    if not filename.lower().endswith(app_config.supported_extensions):
        await message.answer(app_config.format_hint)
        return

    buffer = BytesIO()
    assert message.bot is not None
    await message.bot.download(document, destination=buffer)

    try:
        result = await timetable_service.import_document(filename, buffer.getvalue())
    except TimetableParseError as e:
        await message.answer(f"❌ Не удалось разобрать файл:\n<blockquote>{e}</blockquote>")
        return

    dates = ", ".join(d.strftime("%d.%m.%Y") for d in result.dates)
    await message.answer(
        "✅ Расписание загружено\n"
        f"<blockquote>• Даты: {dates}\n"
        f"• Пар: {result.lessons}\n"
        f"• Групп: {result.groups}</blockquote>"
    )
