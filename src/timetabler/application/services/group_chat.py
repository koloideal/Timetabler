from timetabler.domain.schemas import GroupChat
from timetabler.infrastructure.database.dao import GroupChatsDAO


class GroupChatService:
    def __init__(self, group_chats_dao: GroupChatsDAO) -> None:
        self.group_chats_dao = group_chats_dao

    async def register(self, chat_id: int, title: str | None) -> GroupChat | None:
        return await self.group_chats_dao.upsert(chat_id, title)

    async def unregister(self, chat_id: int) -> bool:
        return await self.group_chats_dao.remove(chat_id)

    async def get_by_id(self, chat_id: int) -> GroupChat | None:
        return await self.group_chats_dao.get_by_id(chat_id)

    async def list_chats(self) -> list[GroupChat]:
        return await self.group_chats_dao.get_all()
