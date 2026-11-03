import asyncio
import os
import sys
from logging import Logger, getLogger

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums.parse_mode import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram_dialog import setup_dialogs
from dishka import make_async_container
from dishka.integrations.aiogram import setup_dishka

from timetabler.infrastructure.config import load_config
from timetabler.infrastructure.config.models import Config
from timetabler.infrastructure.ioc import DatabaseProvider, ParsersProvider, ServicesProvider
from timetabler.infrastructure.logging.logger import setup_logging
from timetabler.presentation.middlewares.check_ban import CheckBanMiddleware
from timetabler.presentation.middlewares.reject_not_creator import RejectNotCreatorMiddleware
from timetabler.presentation.middlewares.reject_not_staff import RejectNotStaffMiddleware

config: Config = load_config("secret_data/config.toml")

session = AiohttpSession()
bot: Bot = Bot(
    token=config.bot.token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    session=session,
)

logger: Logger = getLogger("main")
os.makedirs("logs", exist_ok=True)
setup_logging("secret_data/logger-config.json")

container = make_async_container(
    DatabaseProvider(),
    ServicesProvider(),
    ParsersProvider(),
    context={Config: config, Bot: bot},
)

dp: Dispatcher = Dispatcher(storage=MemoryStorage())


async def main() -> None:
    from timetabler.presentation.admin_dialogs import admin_panel_dialog
    from timetabler.presentation.admin_handlers import admin_router
    from timetabler.presentation.group_handlers import group_router
    from timetabler.presentation.upload_handlers import upload_router
    from timetabler.presentation.user_handlers import user_router

    dp.include_routers(user_router, admin_router, upload_router, group_router, admin_panel_dialog)

    admin_router.message.middleware(RejectNotCreatorMiddleware())
    admin_panel_dialog.callback_query.middleware(RejectNotCreatorMiddleware())
    upload_router.message.middleware(RejectNotStaffMiddleware())
    dp.update.middleware(CheckBanMiddleware())

    setup_dialogs(dp)
    setup_dishka(router=dp, container=container, auto_inject=True)

    async with container() as nested_container:
        from timetabler.application.services.bot import BotService
        bot_service = await nested_container.get(BotService)
        await bot_service.process_set_commands()

    await bot.delete_webhook(drop_pending_updates=True)

    logger.critical("Starting Timetabler...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.critical("End of work...")
