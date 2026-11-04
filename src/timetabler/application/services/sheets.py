from timetabler.domain.schemas import SheetSource
from datetime import date

from timetabler.infrastructure.database.dao import SheetSourcesDAO
from timetabler.infrastructure.sheets import GoogleSheetsClient


class SheetsService:
    def __init__(self, sheet_sources_dao: SheetSourcesDAO, sheets_client: GoogleSheetsClient) -> None:
        self.sheet_sources_dao = sheet_sources_dao
        self.sheets_client = sheets_client

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

    async def export_xlsx(self, for_date: date) -> bytes | None:
        source = await self.get_source(for_date.weekday())
        if not source or not source.spreadsheet_id:
            return None
        return await self.sheets_client.export_xlsx(source.spreadsheet_id)
