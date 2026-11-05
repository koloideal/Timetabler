from datetime import date, datetime

from timetabler.domain.schemas import ParsedTimetable, ResolvedLesson, Revision
from timetabler.infrastructure.database.dao import RevisionsDAO, StudyGroupsDAO


class RevisionService:
    def __init__(
        self,
        revisions_dao: RevisionsDAO,
        study_groups_dao: StudyGroupsDAO,
    ) -> None:
        self.revisions_dao = revisions_dao
        self.study_groups_dao = study_groups_dao

    async def get_by_id(self, revision_id: int) -> Revision | None:
        return await self.revisions_dao.get_by_id(revision_id)

    async def get_published(self, for_date: date) -> Revision | None:
        return await self.revisions_dao.get_published(for_date)

    async def get_settling(self, for_date: date) -> Revision | None:
        return await self.revisions_dao.get_settling(for_date)

    async def get_by_status(self, status: str) -> list[Revision]:
        return await self.revisions_dao.get_by_status(status)

    async def get_entries(self, revision_id: int) -> list[ResolvedLesson]:
        return await self.revisions_dao.get_entries(revision_id)

    async def latest_group_ids(self) -> list[int]:
        return await self.revisions_dao.latest_group_ids()

    async def create(
        self,
        *,
        for_date: date,
        header: str | None,
        content_hash: str,
        group_hashes: dict[int, str],
        kind: str,
        changed_groups: list[int],
        diff: dict[int, list[str]],
        parent_revision_id: int | None,
        parsed: ParsedTimetable,
    ) -> Revision:
        await self._ensure_study_groups(parsed)
        return await self.revisions_dao.create(
            for_date=for_date,
            header=header,
            content_hash=content_hash,
            group_hashes=group_hashes,
            kind=kind,
            changed_groups=changed_groups,
            diff=diff,
            parent_revision_id=parent_revision_id,
            status="settling",
            parsed=parsed,
        )

    async def refresh_candidate(
        self,
        revision: Revision,
        *,
        header: str | None,
        content_hash: str,
        group_hashes: dict[int, str],
        kind: str,
        changed_groups: list[int],
        diff: dict[int, list[str]],
        parent_revision_id: int | None,
        parsed: ParsedTimetable,
    ) -> Revision | None:
        await self._ensure_study_groups(parsed)
        return await self.revisions_dao.replace_snapshot(
            revision.id,
            header=header,
            content_hash=content_hash,
            group_hashes=group_hashes,
            kind=kind,
            changed_groups=changed_groups,
            diff=diff,
            parent_revision_id=parent_revision_id,
            parsed=parsed,
        )

    async def bump_stable(self, revision_id: int) -> Revision | None:
        return await self.revisions_dao.bump_stable(revision_id)

    async def mark_settled(self, revision_id: int, settled_at: datetime) -> Revision | None:
        return await self.revisions_dao.update_fields(revision_id, settled_at=settled_at)

    async def set_status(self, revision_id: int, status: str) -> Revision | None:
        return await self.revisions_dao.update_fields(revision_id, status=status)

    async def mark_published(self, revision_id: int, published_at: datetime) -> Revision | None:
        return await self.revisions_dao.update_fields(
            revision_id, status="published", published_at=published_at
        )

    async def delete(self, revision_id: int) -> bool:
        return await self.revisions_dao.remove(revision_id)

    async def _ensure_study_groups(self, parsed: ParsedTimetable) -> None:
        known = {g.group_id for g in await self.study_groups_dao.get_all()}
        for group_id in sorted(
            {e.group_id for e in parsed.entries if e.group_id not in known}
        ):
            await self.study_groups_dao.create(group_id, None)
