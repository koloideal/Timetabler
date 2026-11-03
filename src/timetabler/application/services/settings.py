from timetabler.domain.schemas import SheetsSettings
from timetabler.infrastructure.database.dao import SettingsDAO

SETTING_CREDENTIALS_PATH = "sheets.credentials_path"
SETTING_SCHEDULE_RANGE = "sheets.schedule_range"
SETTING_DATE_CELL = "sheets.date_cell"
SETTING_POLL_INTERVAL = "sheets.poll_interval_seconds"

DEFAULT_SCHEDULE_RANGE = "A1:I100"
DEFAULT_DATE_CELL = "A1"
DEFAULT_POLL_INTERVAL_SECONDS = 180


class SettingsService:
    def __init__(self, settings_dao: SettingsDAO) -> None:
        self.settings_dao = settings_dao

    async def get_sheets_settings(self) -> SheetsSettings:
        return SheetsSettings(
            credentials_path=await self.settings_dao.get(SETTING_CREDENTIALS_PATH),
            schedule_range=(
                await self.settings_dao.get(SETTING_SCHEDULE_RANGE) or DEFAULT_SCHEDULE_RANGE
            ),
            date_cell=(
                await self.settings_dao.get(SETTING_DATE_CELL) or DEFAULT_DATE_CELL
            ),
            poll_interval_seconds=int(
                await self.settings_dao.get(SETTING_POLL_INTERVAL)
                or DEFAULT_POLL_INTERVAL_SECONDS
            ),
        )

    async def set(self, key: str, value: str | None) -> None:
        await self.settings_dao.set(key, value)
