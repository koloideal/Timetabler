from timetabler.domain.schemas import SheetsSettings
from timetabler.infrastructure.config.app import SheetsSettingsConfig
from timetabler.infrastructure.database.dao import SettingsDAO


class SettingsService:
    def __init__(self, settings_dao: SettingsDAO, config: SheetsSettingsConfig) -> None:
        self.settings_dao = settings_dao
        self.config = config

    async def get_sheets_settings(self) -> SheetsSettings:
        return SheetsSettings(
            schedule_range=(
                await self.settings_dao.get(self.config.schedule_range_key)
                or self.config.default_schedule_range
            ),
            date_cell=(
                await self.settings_dao.get(self.config.date_cell_key)
                or self.config.default_date_cell
            ),
            poll_interval_seconds=int(
                await self.settings_dao.get(self.config.poll_interval_key)
                or self.config.default_poll_interval_seconds
            ),
            lookahead_poll_seconds=int(
                await self.settings_dao.get(self.config.lookahead_poll_key)
                or self.config.default_lookahead_poll_seconds
            ),
            require_confirmation=bool(
                await self.settings_dao.get(self.config.confirmation_key) == "1"
            ),
        )

    async def set(self, key: str, value: str | None) -> None:
        await self.settings_dao.set(key, value)
