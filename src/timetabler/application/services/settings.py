import json
from datetime import date

from timetabler.domain.schemas import PendingBroadcast, SheetsSettings
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
            require_confirmation=bool(
                await self.settings_dao.get(self.config.confirmation_key) == "1"
            ),
        )

    async def get_pending_broadcast(self) -> PendingBroadcast | None:
        raw = await self.settings_dao.get(self.config.pending_broadcast_key)
        if not raw:
            return None
        data = json.loads(raw)
        return PendingBroadcast(
            weekday=int(data["weekday"]),
            marker=str(data["marker"]),
            dates=[date.fromisoformat(d) for d in data["dates"]],
        )

    async def set_pending_broadcast(self, pending: PendingBroadcast | None) -> None:
        value = None
        if pending is not None:
            value = json.dumps(
                {
                    "weekday": pending.weekday,
                    "marker": pending.marker,
                    "dates": [d.isoformat() for d in pending.dates],
                }
            )
        await self.settings_dao.set(self.config.pending_broadcast_key, value)

    async def set(self, key: str, value: str | None) -> None:
        await self.settings_dao.set(key, value)
