from typing import Protocol

from timetabler.domain.schemas import Revision


class CreatorNotifier(Protocol):
    async def ask_revision_approval(self, revision: Revision) -> None: ...

    async def notify_revision_update(self, revision: Revision) -> None: ...

    async def notify_creator(self, text: str) -> None: ...
