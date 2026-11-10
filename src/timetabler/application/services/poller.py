import asyncio
import logging
from datetime import date, datetime, timedelta
from time import monotonic
from zoneinfo import ZoneInfo

from dishka import AsyncContainer
from sqlalchemy.ext.asyncio import AsyncSession

from timetabler.application.exceptions import TimetableParseError
from timetabler.application.services.broadcast import BroadcastService
from timetabler.application.services.detection import DetectionService
from timetabler.application.services.revision import RevisionService
from timetabler.application.services.settings import SettingsService
from timetabler.infrastructure.config.app import AppConfig
from timetabler.infrastructure.sheets import SheetAccessError


def schedule_today(tz_name: str) -> date:
    return datetime.now(ZoneInfo(tz_name)).date()


def next_study_day(today: date) -> date:
    next_day = today + timedelta(days=1)
    if next_day.weekday() == 6:
        next_day += timedelta(days=1)
    return next_day


def lookahead_day(today: date) -> date:
    return next_study_day(next_study_day(today))


class SheetsPoller:
    def __init__(self, container: AsyncContainer) -> None:
        self.container = container
        self._errors: dict[object, str] = {}
        self._logger = logging.getLogger(__name__)
        self._last_lookahead = 0.0

    async def run(self) -> None:
        app_config = await self.container.get(AppConfig)
        delay = app_config.sheets_settings.default_poll_interval_seconds
        while True:
            try:
                delay = await self.poll_once()
            except Exception:
                self._logger.exception("Sheets poll cycle failed")
            await asyncio.sleep(delay)

    async def poll_once(self) -> int:
        app_config = await self.container.get(AppConfig)
        async with self.container() as scope:
            settings_service: SettingsService = await scope.get(SettingsService)
            detection: DetectionService = await scope.get(DetectionService)
            broadcast_service: BroadcastService = await scope.get(BroadcastService)
            revision_service: RevisionService = await scope.get(RevisionService)

            settings = await settings_service.get_sheets_settings()
            poll_interval = settings.poll_interval_seconds

            approved = await revision_service.get_by_status("approved")

            today = schedule_today(app_config.revisions.update_timezone)
            days = ([today] if today.weekday() < 6 else []) + [next_study_day(today)]
            if monotonic() - self._last_lookahead >= settings.lookahead_poll_seconds:
                self._last_lookahead = monotonic()
                far = lookahead_day(today)
                if far not in days:
                    days.append(far)
            for rev in await revision_service.get_by_status("settling"):
                if rev.for_date >= today and rev.for_date not in days:
                    days.append(rev.for_date)
            for for_date in days:
                try:
                    revision = await detection.poll_day(for_date)
                except (SheetAccessError, TimetableParseError) as e:
                    self._log_error_once(for_date, f"{e}")
                except Exception as e:
                    self._logger.exception("Unexpected poll failure for %s", for_date)
                    self._log_error_once(for_date, f"{type(e).__name__}: {e}")
                else:
                    self._clear_error(for_date)
                    if revision is not None:
                        approved.append(revision)

            settling_dates = {
                r.for_date for r in await revision_service.get_by_status("settling")
            }
            if settling_dates & set(days):
                poll_interval = min(
                    poll_interval, app_config.revisions.settle_poll_seconds
                )

            await (await scope.get(AsyncSession)).commit()
            for revision in approved:
                await broadcast_service.publish_revision(revision)

        return poll_interval

    def _log_error_once(self, key: object, message: str) -> None:
        if self._errors.get(key) != message:
            self._errors[key] = message
            self._logger.error("Sheets poll failed (%s): %s", key, message)

    def _clear_error(self, key: object) -> None:
        if key in self._errors:
            del self._errors[key]
            self._logger.info("Sheets poll recovered (%s)", key)
