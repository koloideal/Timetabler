from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from timetabler.infrastructure.database.models import Setting as OrmSetting


class SettingsDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str) -> str | None:
        query = select(OrmSetting.value).where(OrmSetting.key == key)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def set(self, key: str, value: str | None) -> None:
        stmt = (
            insert(OrmSetting)
            .values(key=key, value=value)
            .on_conflict_do_update(index_elements=["key"], set_={"value": value})
        )
        await self.session.execute(stmt)
        await self.session.flush()
