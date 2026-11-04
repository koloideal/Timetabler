from timetabler.domain.schemas import SheetSource
from timetabler.infrastructure.database.dao import SheetSourcesDAO


class SheetsService:
    def __init__(self, sheet_sources_dao: SheetSourcesDAO) -> None:
        self.sheet_sources_dao = sheet_sources_dao

    async def list_sources(self) -> list[SheetSource]:
        return await self.sheet_sources_dao.get_all()

    async def get_source(self, weekday: int) -> SheetSource | None:
        return await self.sheet_sources_dao.get_by_weekday(weekday)

    async def set_spreadsheet(self, weekday: int, spreadsheet_id: str | None) -> None:
        await self.sheet_sources_dao.set_spreadsheet(weekday, spreadsheet_id)

    async def mark_header(self, weekday: int, last_header: str) -> None:
        await self.sheet_sources_dao.set_last_header(weekday, last_header)

    async def set_last_hash(self, weekday: int, last_hash: str) -> None:
        await self.sheet_sources_dao.set_last_hash(weekday, last_hash)
