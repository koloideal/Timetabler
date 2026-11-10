from dataclasses import dataclass, field

from timetabler.domain.groups import course_of, specialty_code, specialty_labels
from timetabler.domain.schemas import StudyGroup
from timetabler.infrastructure.database.dao import (
    GroupChatsDAO,
    StudyGroupsDAO,
    UsersDAO,
)

MODE_ALL = "all"
MODE_COURSES = "courses"
MODE_SPECIALTIES = "specialties"
MODE_GROUPS = "groups"


@dataclass
class AudienceSpec:
    mode: str = MODE_ALL
    values: list[str] = field(default_factory=list)
    include_chats: bool = True


@dataclass
class Audience:
    user_ids: list[int] = field(default_factory=list)
    chat_ids: list[int] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.user_ids) + len(self.chat_ids)


class AudienceService:
    def __init__(
        self,
        users_dao: UsersDAO,
        group_chats_dao: GroupChatsDAO,
        study_groups_dao: StudyGroupsDAO,
    ) -> None:
        self.users_dao = users_dao
        self.group_chats_dao = group_chats_dao
        self.study_groups_dao = study_groups_dao

    async def options(self, mode: str) -> list[tuple[str, str]]:
        groups = await self.study_groups_dao.get_all()
        if mode == MODE_COURSES:
            courses = sorted({c for g in groups if (c := course_of(g)) is not None})
            return [(f"{c} курс", str(c)) for c in courses]
        if mode == MODE_SPECIALTIES:
            labels = specialty_labels(groups)
            return [(labels[c], c) for c in sorted(labels)]
        return [(str(g.group_id), str(g.group_id)) for g in sorted(groups, key=lambda g: g.group_id)]

    @staticmethod
    def target_groups(spec: AudienceSpec, groups: list[StudyGroup]) -> set[int] | None:
        if spec.mode == MODE_ALL:
            return None
        wanted = set(spec.values)
        if spec.mode == MODE_COURSES:
            return {g.group_id for g in groups if str(course_of(g)) in wanted}
        if spec.mode == MODE_SPECIALTIES:
            return {g.group_id for g in groups if specialty_code(g) in wanted}
        return {g.group_id for g in groups if str(g.group_id) in wanted}

    async def resolve(self, spec: AudienceSpec) -> Audience:
        targets = self.target_groups(spec, await self.study_groups_dao.get_all())
        users = [u for u in await self.users_dao.get_all() if not u.is_banned]
        audience = Audience()
        if targets is None:
            audience.user_ids = [u.user_id for u in users]
        else:
            wanted = {str(g) for g in targets}
            audience.user_ids = [u.user_id for u in users if wanted & set(u.groups)]
        if spec.include_chats:
            chats = await self.group_chats_dao.get_active()
            audience.chat_ids = [
                c.chat_id
                for c in chats
                if targets is None or targets & set(c.study_groups)
            ]
        return audience
