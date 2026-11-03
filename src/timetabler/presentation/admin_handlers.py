import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram_dialog import DialogManager, StartMode

from timetabler.presentation.admin_dialogs.admin_panel import AdminPanelSG

logger = logging.getLogger(__name__)

admin_router = Router()


@admin_router.message(Command("admin"))
async def admin_panel_entry(message: Message, dialog_manager: DialogManager) -> None:
    await dialog_manager.start(AdminPanelSG.main, mode=StartMode.RESET_STACK)
