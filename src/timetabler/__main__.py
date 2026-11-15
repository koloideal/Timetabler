import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from logging import Logger, getLogger

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums.parse_mode import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram_dialog import setup_dialogs
from dishka import make_async_container
from dishka.integrations.aiogram import setup_dishka

from timetabler.application.services.poller import SheetsPoller
from timetabler.infrastructure.config import load_config
from timetabler.infrastructure.config.models import Config
from timetabler.infrastructure.ioc import (
    AppConfigProvider,
    DatabaseProvider,
    ParsersProvider,
    PresentationProvider,
    ServicesProvider,
    SheetsProvider,
)
from timetabler.infrastructure.logging.logger import setup_logging
from timetabler.presentation.middlewares.check_ban import CheckBanMiddleware
from timetabler.presentation.middlewares.reject_not_creator import RejectNotCreatorMiddleware


class KeepaliveAiohttpSession(AiohttpSession):
    def __init__(self) -> None:
        super().__init__()
        self._connector_init["keepalive_timeout"] = 3600


async def _startup_call(
    logger: Logger,
    label: str,
    call: Callable[[], Awaitable[object]],
    attempts: int = 6,
    delay: float = 2.0,
) -> None:
    for attempt in range(1, attempts + 1):
        try:
            await call()
            return
        except TelegramNetworkError as e:
            if attempt == attempts:
                break
            logger.warning(
                "%s failed: %s — retry in %.0fs (%d/%d)",
                label, e, delay, attempt, attempts,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)
    logger.warning("%s skipped after %d attempts — continuing startup", label, attempts)


async def main() -> None:
    from timetabler.presentation.admin_dialogs import build_admin_panel_dialog
    from timetabler.presentation.admin_handlers import new_admin_router
    from timetabler.presentation.error_handlers import new_error_router
    from timetabler.presentation.group_handlers import new_group_router
    from timetabler.presentation.telegram import TelegramNotifier
    from timetabler.presentation.user_dialogs import (
        build_group_setup_dialog,
        build_user_menu_dialog,
    )
    from timetabler.presentation.user_handlers import new_user_router

    config: Config = load_config("secret_data/config.toml")
    logger = getLogger("main")
    os.makedirs("logs", exist_ok=True)
    setup_logging("secret_data/logger-config.json")

    bot: Bot = Bot(
        token=config.bot.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=KeepaliveAiohttpSession(),
    )

    container = make_async_container(
        DatabaseProvider(),
        ServicesProvider(),
        SheetsProvider(),
        ParsersProvider(),
        PresentationProvider(),
        AppConfigProvider(),
        context={Config: config, Bot: bot},
    )

    dp: Dispatcher = Dispatcher(storage=MemoryStorage())

    admin_router = new_admin_router()
    admin_panel_dialog = build_admin_panel_dialog()
    dp.include_routers(
        new_error_router(),
        new_user_router(),
        admin_router,
        new_group_router(),
        admin_panel_dialog,
        build_user_menu_dialog(),
        build_group_setup_dialog(),
    )

    admin_router.message.middleware(RejectNotCreatorMiddleware())
    admin_router.callback_query.middleware(RejectNotCreatorMiddleware())
    admin_panel_dialog.callback_query.middleware(RejectNotCreatorMiddleware())
    dp.update.middleware(CheckBanMiddleware())

    setup_dialogs(dp)
    setup_dishka(router=dp, container=container, auto_inject=True)

    async with container() as nested_container:
        notifier = await nested_container.get(TelegramNotifier)
        await _startup_call(logger, "set_my_commands", notifier.process_set_commands)

    await _startup_call(
        logger,
        "delete_webhook",
        lambda: bot.delete_webhook(drop_pending_updates=True),
    )

    poller = SheetsPoller(container)
    poll_task = asyncio.create_task(poller.run())

    logger.critical("Starting Timetabler...")
    try:
        await dp.start_polling(bot)
    finally:
        poll_task.cancel()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        getLogger("main").critical("End of work...")
