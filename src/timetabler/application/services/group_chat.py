from timetabler.domain.schemas import GroupChat
from timetabler.infrastructure.database.dao import GroupChatsDAO


class GroupChatService:
    def __init__(self, group_chats_dao: GroupChatsDAO) -> None:
        self.group_chats_dao = group_chats_dao

    async def register(self, chat_id: int, title: str | None, added_by_user_id: int | None) -> GroupChat | None:
        return await self.group_chats_dao.upsert(chat_id, title, added_by_user_id)

    async def mark_removed(self, chat_id: int) -> GroupChat | None:
        return await self.group_chats_dao.set_status(chat_id, "disabled")

    async def get_by_id(self, chat_id: int) -> GroupChat | None:
        return await self.group_chats_dao.get_by_id(chat_id)

    async def list_chats(self) -> list[GroupChat]:
        return await self.group_chats_dao.get_all()

    async def get_pending_for_user(self, user_id: int) -> list[GroupChat]:
        return await self.group_chats_dao.get_pending_for_user(user_id)

    async def select_groups(
        self, chat_id: int, study_groups: list[int], configured_by_user_id: int
    ) -> GroupChat | None:
        return await self.group_chats_dao.set_study_groups(chat_id, study_groups, configured_by_user_id)

    async def set_enabled(self, chat_id: int, enabled: bool) -> GroupChat | None:
        return await self.group_chats_dao.set_status(chat_id, "active" if enabled else "disabled")

    async def set_pin(self, chat_id: int, enabled: bool) -> GroupChat | None:
        return await self.group_chats_dao.set_pin_enabled(chat_id, enabled)

    async def set_pinned_messages(self, chat_id: int, message_ids: list[int]) -> GroupChat | None:
        return await self.group_chats_dao.set_pinned_messages(chat_id, message_ids)
