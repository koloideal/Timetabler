import logging

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.enums.chat_type import ChatType
from aiogram.filters import Command
from aiogram.types import ChatMemberUpdated, Message
from dishka import FromDishka

from timetabler.application.services.channel import ChannelService
from timetabler.application.services.group_chat import GroupChatService
from timetabler.infrastructure.config.models import Config
from timetabler.presentation.messages import channel_approval_markup
from timetabler.presentation.telegram import TelegramNotifier


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
        channel_service: FromDishka[ChannelService],
        notifier: FromDishka[TelegramNotifier],
        config: FromDishka[Config],
    ) -> None:
        status = event.new_chat_member.status

        if event.chat.type == ChatType.CHANNEL:
            if status == ChatMemberStatus.ADMINISTRATOR:
                await channel_service.register_pending(event.chat.id, event.chat.title)
                logger.info("Bot added to channel %s (%s)", event.chat.id, event.chat.title)
                title = event.chat.title or str(event.chat.id)
                if event.from_user and event.from_user.id == config.bot.creator_id:
                    await channel_service.approve(event.chat.id)
                    await notifier.notify_creator(
                        f"📢 Канал «{title}» одобрен автоматически и включён в рассылку."
                    )
                else:
                    byline = f" от @{event.from_user.username}" if event.from_user and event.from_user.username else ""
                    await notifier.notify_creator(
                        f"📢 Меня добавили в канал «{title}» (<code>{event.chat.id}</code>){byline}.\nРазрешить?",
                        reply_markup=channel_approval_markup(event.chat.id),
                    )
            elif status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
                await channel_service.remove(event.chat.id)
                logger.info("Bot removed from channel %s", event.chat.id)
            return

        if event.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            return

        if status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
            await group_chat_service.register(event.chat.id, event.chat.title)
            logger.info("Bot added to chat %s (%s)", event.chat.id, event.chat.title)
        elif status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
            await group_chat_service.unregister(event.chat.id)
            logger.info("Bot removed from chat %s", event.chat.id)

    return router
