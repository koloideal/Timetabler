from timetabler.domain.schemas import StudyGroup
from timetabler.infrastructure.database.dao import StudyGroupsDAO


class StudyGroupService:
    def __init__(self, study_groups_dao: StudyGroupsDAO) -> None:
        self.study_groups_dao = study_groups_dao

    async def list_groups(self) -> list[StudyGroup]:
        return await self.study_groups_dao.get_all()

    async def get_by_id(self, group_id: int) -> StudyGroup | None:
        return await self.study_groups_dao.get_by_id(group_id)

    async def create_group(self, group_id: int, alias: str | None) -> StudyGroup | None:
        return await self.study_groups_dao.create(group_id, alias)

    async def delete_group(self, group_id: int) -> bool:
        return await self.study_groups_dao.remove(group_id)
