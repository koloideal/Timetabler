import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from dishka import AsyncContainer

from timetabler.application.exceptions import TimetableParseError
from timetabler.application.ports import ScheduleParser
from timetabler.application.services.bot import BotService
from timetabler.application.services.broadcast import BroadcastService
from timetabler.application.services.settings import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    SettingsService,
)
from timetabler.application.services.sheets import SheetsService
from timetabler.application.services.timetable import TimetableService
from timetabler.application.services.user import UserService
from timetabler.infrastructure.config.app import AppConfig
from timetabler.infrastructure.config.models import Config
from timetabler.infrastructure.sheets import GoogleSheetsClient, SheetAccessError

logger = logging.getLogger(__name__)

CONFIG_ERROR_KEY = "config"


def next_study_day(today: date) -> date:
    next_day = today + timedelta(days=1)
    if next_day.weekday() == 6:
        next_day += timedelta(days=1)
    return next_day


class SheetsPoller:
    def __init__(self, container: AsyncContainer) -> None:
        self.container = container
        self._errors: dict[int | str, str] = {}

    async def run(self) -> None:
        while True:
            try:
                delay = await self.poll_once()
            except Exception:
                logger.exception("Sheets poll cycle failed")
                delay = DEFAULT_POLL_INTERVAL_SECONDS
            await asyncio.sleep(delay)

    async def poll_once(self) -> int:
        target_date = next_study_day(date.today())
        weekday = target_date.weekday()

        async with self.container() as scope:
            config: Config = await scope.get(Config)
            app_config: AppConfig = await scope.get(AppConfig)
            client: GoogleSheetsClient = await scope.get(GoogleSheetsClient)
            parser: ScheduleParser = await scope.get(ScheduleParser)
            settings_service: SettingsService = await scope.get(SettingsService)
            sheets_service: SheetsService = await scope.get(SheetsService)
            user_service: UserService = await scope.get(UserService)
            timetable_service: TimetableService = await scope.get(TimetableService)
            broadcast_service: BroadcastService = await scope.get(BroadcastService)
            bot_service: BotService = await scope.get(BotService)

            settings = await settings_service.get_sheets_settings()
            if not settings.credentials_path:
                self._log_error_once(CONFIG_ERROR_KEY, "не задан путь к ключу сервисного аккаунта")
                return settings.poll_interval_seconds
            try:
                client.configure(settings.credentials_path)
            except Exception as e:
                self._log_error_once(CONFIG_ERROR_KEY, f"не удалось загрузить ключ: {e}")
                return settings.poll_interval_seconds
            self._clear_error(CONFIG_ERROR_KEY)

            source = await sheets_service.get_source(weekday)
            if not source or not source.spreadsheet_id:
                return settings.poll_interval_seconds

            try:
                marker = await self._read_marker(client, source.spreadsheet_id, settings.date_cell)
                if not marker or marker == source.last_header:
                    self._clear_error(weekday)
                    return settings.poll_interval_seconds

                values = await client.read_values(source.spreadsheet_id, settings.schedule_range)
                parsed = parser.parse(values, default_date=target_date)

                await user_service.get_or_create(config.bot.creator_id, None)
                result = await timetable_service.import_parsed(
                    parsed, source.spreadsheet_id, config.bot.creator_id
                )
            except (SheetAccessError, TimetableParseError) as e:
                self._log_error_once(weekday, f"{e}")
                return settings.poll_interval_seconds
            except Exception as e:
                self._log_error_once(weekday, f"{type(e).__name__}: {e}")
                return settings.poll_interval_seconds
            self._clear_error(weekday)

            total_sent = total_failed = chats_sent = chats_failed = 0
            for for_date in result.dates:
                report = await broadcast_service.broadcast(for_date)
                total_sent += report.users_sent
                total_failed += report.users_failed
                chats_sent += report.chats_sent
                chats_failed += report.chats_failed

            await sheets_service.mark_header(weekday, marker)

            dates = ", ".join(d.strftime("%d.%m.%Y") for d in result.dates)
            await bot_service.notify_creator(
                "📊 <b>РАСПИСАНИЕ ОБНОВЛЕНО</b>\n"
                f"<pre>ДЕНЬ     {app_config.weekdays_short[weekday]} ({dates})\n"
                f"ПАР      {result.lessons}\n"
                f"ГРУПП    {result.groups}\n"
                f"ЮЗЕРАМ   {total_sent} (+{total_failed} недост.)\n"
                f"ЧАТАМ    {chats_sent} (+{chats_failed} недост.)</pre>"
            )
            logger.info(
                "Sheet %s: broadcast %s for weekday %s",
                source.spreadsheet_id, dates, weekday,
            )
            return settings.poll_interval_seconds

    async def _read_marker(
        self, client: GoogleSheetsClient, spreadsheet_id: str, date_cell: str
    ) -> str:
        values: list[list[Any]] = await client.read_values(spreadsheet_id, date_cell)
        if not values or not values[0]:
            return ""
        return str(values[0][0])

    def _log_error_once(self, key: int | str, message: str) -> None:
        if self._errors.get(key) != message:
            self._errors[key] = message
            logger.error("Sheets poll failed (%s): %s", key, message)

    def _clear_error(self, key: int | str) -> None:
        if key in self._errors:
            del self._errors[key]
            logger.info("Sheets poll recovered (%s)", key)
