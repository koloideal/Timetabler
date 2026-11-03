import logging

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.enums.chat_type import ChatType
from aiogram.filters import Command
from aiogram.types import ChatMemberUpdated, Message
from dishka import FromDishka

from timetabler.application.services.group_chat import GroupChatService


def new_group_router() -> Router:
    router = Router()
    router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
    logger = logging.getLogger(__name__)

    @router.message(Command("start"))
    async def group_start(message: Message) -> None:
        await message.answer(
            "👋 <b>TIMETABLER</b>\n━━━━━━━━━━━━━━━━━━\n"
            "Буду присылать расписание в этот чат.\n\n"
            "<i>Настройка групп появится позже.</i>"
        )

    @router.my_chat_member()
    async def on_bot_membership_change(
        event: ChatMemberUpdated,
        group_chat_service: FromDishka[GroupChatService],
    ) -> None:
        if event.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            return

        status = event.new_chat_member.status
        if status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
            await group_chat_service.register(event.chat.id, event.chat.title)
            logger.info("Bot added to chat %s (%s)", event.chat.id, event.chat.title)
        elif status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
            await group_chat_service.unregister(event.chat.id)
            logger.info("Bot removed from chat %s", event.chat.id)

    return router
