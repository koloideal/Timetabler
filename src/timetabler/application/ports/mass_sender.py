from typing import Protocol

COPY_OK = "ok"
COPY_BLOCKED = "blocked"
COPY_FAILED = "failed"


class MassSender(Protocol):
    async def copy_to(self, chat_id: int, from_chat_id: int, message_id: int) -> str: ...
