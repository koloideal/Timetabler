from timetabler.domain.schemas import Channel
from timetabler.infrastructure.database.dao import ChannelsDAO


class ChannelService:
    def __init__(self, channels_dao: ChannelsDAO) -> None:
        self.channels_dao = channels_dao

    async def register_pending(self, chat_id: int, title: str | None) -> Channel | None:
        return await self.channels_dao.upsert_pending(chat_id, title)

    async def get_by_id(self, chat_id: int) -> Channel | None:
        return await self.channels_dao.get_by_id(chat_id)

    async def list_channels(self) -> list[Channel]:
        return await self.channels_dao.get_all()

    async def get_enabled(self) -> list[Channel]:
        return await self.channels_dao.get_enabled()

    async def approve(self, chat_id: int) -> Channel | None:
        return await self.channels_dao.set_status(chat_id, "approved")

    async def disable(self, chat_id: int) -> Channel | None:
        return await self.channels_dao.set_status(chat_id, "disabled")

    async def remove(self, chat_id: int) -> bool:
        return await self.channels_dao.remove(chat_id)
