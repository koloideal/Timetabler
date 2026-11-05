from datetime import date

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from timetabler.domain.schemas import ParsedTimetable, ResolvedLesson, Revision
from timetabler.infrastructure.database.models import (
    TimetableRevision as OrmRevision,
)
from timetabler.infrastructure.database.models import (
    TimetableRevisionEntry as OrmEntry,
)


class RevisionsDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, revision_id: int) -> Revision | None:
        query = select(OrmRevision).where(OrmRevision.id == revision_id)
        result = await self.session.execute(query)
        orm_rev = result.scalar_one_or_none()

        if orm_rev:
            return self._map_to_domain(orm_rev)

        return None

    async def get_published(self, for_date: date) -> Revision | None:
        query = (
            select(OrmRevision)
            .where(
                OrmRevision.for_date == for_date,
                OrmRevision.status == "published",
            )
            .order_by(OrmRevision.id.desc())
            .limit(1)
        )
        result = await self.session.execute(query)
        orm_rev = result.scalar_one_or_none()

        if orm_rev:
            return self._map_to_domain(orm_rev)

        return None

    async def get_settling(self, for_date: date) -> Revision | None:
        query = (
            select(OrmRevision)
            .where(
                OrmRevision.for_date == for_date,
                OrmRevision.status == "settling",
            )
            .order_by(OrmRevision.id.desc())
            .limit(1)
        )
        result = await self.session.execute(query)
        orm_rev = result.scalar_one_or_none()

        if orm_rev:
            return self._map_to_domain(orm_rev)

        return None

    async def get_by_status(self, status: str) -> list[Revision]:
        query = select(OrmRevision).where(OrmRevision.status == status).order_by(OrmRevision.id)
        result = await self.session.execute(query)
        return [self._map_to_domain(r) for r in result.scalars().all()]

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
        status: str,
        parsed: ParsedTimetable,
    ) -> Revision:
        orm_rev = OrmRevision(
            for_date=for_date,
            weekday=for_date.weekday(),
            header=header,
            content_hash=content_hash,
            group_hashes={str(g): h for g, h in group_hashes.items()},
            base_audiences={str(g): a for g, a in parsed.base_audiences.items()},
            kind=kind,
            changed_groups=changed_groups,
            diff={str(g): lines for g, lines in diff.items()},
            parent_revision_id=parent_revision_id,
            status=status,
        )
        self.session.add(orm_rev)
        await self.session.flush()

        self._insert_entries(orm_rev.id, parsed.resolved or parsed.entries)
        await self.session.flush()

        return self._map_to_domain(orm_rev)

    async def replace_snapshot(
        self,
        revision_id: int,
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
        stmt = (
            update(OrmRevision)
            .where(OrmRevision.id == revision_id)
            .values(
                header=header,
                content_hash=content_hash,
                group_hashes={str(g): h for g, h in group_hashes.items()},
                base_audiences={str(g): a for g, a in parsed.base_audiences.items()},
                kind=kind,
                changed_groups=changed_groups,
                diff={str(g): lines for g, lines in diff.items()},
                parent_revision_id=parent_revision_id,
                stable_polls=0,
            )
            .returning(OrmRevision)
        )
        result = await self.session.execute(stmt)
        orm_rev = result.scalar_one_or_none()

        if not orm_rev:
            return None

        await self.session.execute(
            delete(OrmEntry).where(OrmEntry.revision_id == revision_id)
        )
        self._insert_entries(revision_id, parsed.resolved or parsed.entries)
        await self.session.flush()

        return self._map_to_domain(orm_rev)

    async def bump_stable(self, revision_id: int) -> Revision | None:
        stmt = (
            update(OrmRevision)
            .where(OrmRevision.id == revision_id)
            .values(stable_polls=OrmRevision.stable_polls + 1)
            .returning(OrmRevision)
        )
        result = await self.session.execute(stmt)
        orm_rev = result.scalar_one_or_none()

        if not orm_rev:
            return None

        return self._map_to_domain(orm_rev)

    async def update_fields(self, revision_id: int, **values: object) -> Revision | None:
        stmt = (
            update(OrmRevision)
            .where(OrmRevision.id == revision_id)
            .values(**values)
            .returning(OrmRevision)
        )
        result = await self.session.execute(stmt)
        orm_rev = result.scalar_one_or_none()

        if not orm_rev:
            return None

        return self._map_to_domain(orm_rev)

    async def get_entries(self, revision_id: int) -> list[ResolvedLesson]:
        rev = await self.get_by_id(revision_id)
        if not rev:
            return []
        query = (
            select(OrmEntry)
            .where(OrmEntry.revision_id == revision_id)
            .order_by(OrmEntry.study_group_id, OrmEntry.ordinal, OrmEntry.position)
        )
        result = await self.session.execute(query)
        return [
            ResolvedLesson(
                group_id=e.study_group_id,
                date=rev.for_date,
                position=e.position,
                subgroup=e.subgroup,
                ordinal=e.ordinal or 0,
                slot=e.slot,
                half=e.half or "full",
                start=e.start_sec,
                end=e.end_sec,
                kind=e.kind or "lesson",
                subject=e.subject,
                teacher=e.teacher,
                audience=e.audience,
                flags=frozenset(e.flags or []),
                source_time=e.starts_at,
            )
            for e in result.scalars().all()
        ]

    async def latest_group_ids(self) -> list[int]:
        latest_id = await self.session.scalar(
            select(OrmRevision.id)
            .where(OrmRevision.status != "rejected")
            .order_by(OrmRevision.id.desc())
            .limit(1)
        )
        if latest_id is None:
            return []
        query = (
            select(OrmEntry.study_group_id)
            .where(OrmEntry.revision_id == latest_id)
            .distinct()
            .order_by(OrmEntry.study_group_id)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def remove(self, revision_id: int) -> bool:
        stmt = delete(OrmRevision).where(OrmRevision.id == revision_id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    def _insert_entries(self, revision_id: int, entries: list) -> None:
        for entry in entries:
            self.session.add(
                OrmEntry(
                    revision_id=revision_id,
                    study_group_id=entry.group_id,
                    position=entry.position,
                    subject=entry.subject,
                    teacher=entry.teacher,
                    audience=entry.audience,
                    starts_at=getattr(entry, "source_time", getattr(entry, "starts_at", None)),
                    subgroup=entry.subgroup,
                    ordinal=getattr(entry, "ordinal", None),
                    slot=getattr(entry, "slot", None),
                    half=getattr(entry, "half", None),
                    start_sec=getattr(entry, "start", None),
                    end_sec=getattr(entry, "end", None),
                    kind=getattr(entry, "kind", None),
                    flags=sorted(getattr(entry, "flags", ()) or ()),
                )
            )

    @staticmethod
    def _map_to_domain(orm_rev: OrmRevision) -> Revision:
        return Revision(
            id=orm_rev.id,
            for_date=orm_rev.for_date,
            weekday=orm_rev.weekday,
            header=orm_rev.header,
            content_hash=orm_rev.content_hash,
            group_hashes={int(g): h for g, h in (orm_rev.group_hashes or {}).items()},
            base_audiences={int(g): a for g, a in (orm_rev.base_audiences or {}).items()},
            kind=orm_rev.kind,
            changed_groups=[int(g) for g in (orm_rev.changed_groups or [])],
            diff={int(g): list(lines) for g, lines in (orm_rev.diff or {}).items()},
            parent_revision_id=orm_rev.parent_revision_id,
            status=orm_rev.status,
            stable_polls=orm_rev.stable_polls,
            detected_at=orm_rev.detected_at,
            settled_at=orm_rev.settled_at,
            published_at=orm_rev.published_at,
        )
