from aiogram import Router
from aiogram.filters import ExceptionTypeFilter
from aiogram.types import ErrorEvent
from aiogram_dialog import DialogManager, StartMode
from aiogram_dialog.api.exceptions import (
    NoContextError,
    OutdatedIntent,
    UnknownIntent,
    UnknownState,
)
from dishka import FromDishka

from timetabler.application.services.user import UserService
from timetabler.infrastructure.config.models import Config
from timetabler.presentation.admin_dialogs import AdminPanelSG
from timetabler.presentation.user_dialogs import UserMenuSG


def _extract_user_id(event: ErrorEvent) -> int | None:
    if event.update.message and event.update.message.from_user:
        return event.update.message.from_user.id
    if event.update.callback_query and event.update.callback_query.from_user:
        return event.update.callback_query.from_user.id
    return None


async def _restart_menu(
    event: ErrorEvent,
    dialog_manager: DialogManager,
    config: Config,
    user_service: UserService,
) -> None:
    user_id = _extract_user_id(event)
    if user_id is None:
        return

    await dialog_manager.reset_stack()
    if user_id == config.bot.creator_id:
        await dialog_manager.start(AdminPanelSG.main, mode=StartMode.RESET_STACK)
        return

    username = None
    if event.update.message and event.update.message.from_user:
        username = event.update.message.from_user.username
    elif event.update.callback_query and event.update.callback_query.from_user:
        username = event.update.callback_query.from_user.username
    await user_service.get_or_create(user_id, username)
    await dialog_manager.start(UserMenuSG.main, mode=StartMode.RESET_STACK)


def new_error_router() -> Router:
    router = Router(name="error_handler")

    @router.error(ExceptionTypeFilter(UnknownIntent))
    async def unknown_intent_handler(
        event: ErrorEvent,
        dialog_manager: DialogManager,
        config: FromDishka[Config],
        user_service: FromDishka[UserService],
    ) -> None:
        if not isinstance(event.exception, UnknownIntent):
            raise event.exception
        await _restart_menu(event, dialog_manager, config, user_service)

    @router.error(ExceptionTypeFilter(OutdatedIntent))
    async def outdated_intent_handler(
        event: ErrorEvent,
        dialog_manager: DialogManager,
        config: FromDishka[Config],
        user_service: FromDishka[UserService],
    ) -> None:
        if not isinstance(event.exception, OutdatedIntent):
            raise event.exception
        await _restart_menu(event, dialog_manager, config, user_service)

    @router.error(ExceptionTypeFilter(UnknownState))
    async def unknown_state_handler(
        event: ErrorEvent,
        dialog_manager: DialogManager,
        config: FromDishka[Config],
        user_service: FromDishka[UserService],
    ) -> None:
        if not isinstance(event.exception, UnknownState):
            raise event.exception
        await _restart_menu(event, dialog_manager, config, user_service)

    @router.error(ExceptionTypeFilter(NoContextError))
    async def no_context_handler(
        event: ErrorEvent,
        dialog_manager: DialogManager,
        config: FromDishka[Config],
        user_service: FromDishka[UserService],
    ) -> None:
        if not isinstance(event.exception, NoContextError):
            raise event.exception
        await _restart_menu(event, dialog_manager, config, user_service)

    return router
