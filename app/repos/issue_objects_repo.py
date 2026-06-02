from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.issue_object import IssueObject, IssueObjectAlias

_NON_WORD_RE = re.compile(r"[^\w\s]+", flags=re.UNICODE)
_SPACES_RE = re.compile(r"\s+", flags=re.UNICODE)


def normalize_issue_object_name(value: str) -> str:
    text = (value or "").strip().lower().replace("ё", "е")
    text = _NON_WORD_RE.sub(" ", text)
    text = _SPACES_RE.sub(" ", text).strip()
    return text


class IssueObjectsRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, issue_object_id: int) -> IssueObject | None:
        return await self.session.get(IssueObject, issue_object_id)

    async def get_active_by_normalized_key(self, normalized_key: str) -> IssueObject | None:
        stmt = select(IssueObject).where(
            and_(
                IssueObject.normalized_key == normalized_key,
                IssueObject.merged_into_id.is_(None),
                IssueObject.is_active.is_(True),
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_alias_normalized_key(self, normalized_key: str) -> IssueObject | None:
        stmt = (
            select(IssueObject)
            .join(IssueObjectAlias, IssueObjectAlias.issue_object_id == IssueObject.id)
            .where(
                and_(
                    IssueObjectAlias.normalized_key == normalized_key,
                    IssueObject.is_active.is_(True),
                    IssueObject.merged_into_id.is_(None),
                )
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_or_create_by_name(
        self,
        *,
        display_name: str,
        object_type: str = "person",
        code: str | None = None,
    ) -> IssueObject:
        normalized_key = normalize_issue_object_name(display_name)
        if not normalized_key:
            raise ValueError("issue_object display_name is empty after normalization")

        existing = await self.get_active_by_normalized_key(normalized_key)
        if existing is not None:
            return existing

        alias_match = await self.get_by_alias_normalized_key(normalized_key)
        if alias_match is not None:
            return alias_match

        issue_object = IssueObject(
            object_type=object_type,
            display_name=display_name.strip(),
            normalized_key=normalized_key,
            code=code,
            is_active=True,
        )
        self.session.add(issue_object)
        await self.session.flush()
        await self.session.refresh(issue_object)
        return issue_object

    async def create_issue_object(
        self,
        *,
        display_name: str,
        object_type: str = "person",
        code: str | None = None,
    ) -> IssueObject:
        normalized_key = normalize_issue_object_name(display_name)
        if not normalized_key:
            raise ValueError("issue_object display_name is empty after normalization")

        existing = await self.get_active_by_normalized_key(normalized_key)
        if existing is not None:
            return existing

        issue_object = IssueObject(
            object_type=object_type,
            display_name=display_name.strip(),
            normalized_key=normalized_key,
            code=code,
            is_active=True,
        )
        self.session.add(issue_object)
        await self.session.flush()
        await self.session.refresh(issue_object)
        return issue_object

    async def list_issue_objects(
        self,
        *,
        search: str | None,
        object_type: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[IssueObject], int]:
        stmt = select(IssueObject).where(IssueObject.merged_into_id.is_(None))
        count_stmt = select(func.count()).select_from(IssueObject).where(IssueObject.merged_into_id.is_(None))

        if object_type:
            stmt = stmt.where(IssueObject.object_type == object_type)
            count_stmt = count_stmt.where(IssueObject.object_type == object_type)

        if search:
            normalized = normalize_issue_object_name(search)
            term = f"%{search.strip()}%"
            normalized_term = f"%{normalized}%"
            stmt = stmt.where(
                or_(
                    IssueObject.display_name.ilike(term),
                    IssueObject.code.ilike(term) if IssueObject.code is not None else false(),
                    IssueObject.normalized_key.ilike(normalized_term),
                )
            )
            count_stmt = count_stmt.where(
                or_(
                    IssueObject.display_name.ilike(term),
                    IssueObject.code.ilike(term) if IssueObject.code is not None else false(),
                    IssueObject.normalized_key.ilike(normalized_term),
                )
            )

        total_count = (await self.session.execute(count_stmt)).scalar_one()
        stmt = (
            stmt.order_by(IssueObject.display_name, IssueObject.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        issue_objects = list((await self.session.execute(stmt)).scalars().all())
        return issue_objects, int(total_count)

    async def find_similar(
        self,
        *,
        display_name: str,
        limit: int = 5,
    ) -> list[IssueObject]:
        normalized = normalize_issue_object_name(display_name)
        if not normalized:
            return []

        term = f"%{normalized}%"
        stmt = (
            select(IssueObject)
            .where(
                and_(
                    IssueObject.merged_into_id.is_(None),
                    IssueObject.is_active.is_(True),
                    IssueObject.normalized_key.ilike(term),
                )
            )
            .order_by(IssueObject.display_name, IssueObject.id)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def merge_issue_objects(self, *, source_id: int, target_id: int) -> IssueObject:
        if source_id == target_id:
            raise ValueError("cannot merge issue_object into itself")

        source = await self.get_by_id(source_id)
        target = await self.get_by_id(target_id)
        if source is None or target is None:
            raise ValueError("issue_object not found")

        source.is_active = False
        source.merged_into_id = target.id

        alias_exists_stmt = select(IssueObjectAlias).where(IssueObjectAlias.normalized_key == source.normalized_key)
        alias_exists = (await self.session.execute(alias_exists_stmt)).scalar_one_or_none()
        if alias_exists is None:
            alias = IssueObjectAlias(
                issue_object_id=target.id,
                alias=source.display_name,
                normalized_key=source.normalized_key,
            )
            self.session.add(alias)

        await self.session.flush()
        await self.session.refresh(target)
        return target

    async def update_issue_object(
        self,
        issue_object_id: int,
        *,
        display_name: str | None = None,
        object_type: str | None = None,
        code: str | None = None,
        is_active: bool | None = None,
    ) -> IssueObject:
        issue_object = await self.get_by_id(issue_object_id)
        if not issue_object:
            raise ValueError(f"IssueObject {issue_object_id} not found")
        if issue_object.deleted_at is not None:
            raise ValueError(f"IssueObject {issue_object_id} is deleted")
        if display_name is not None:
            issue_object.display_name = display_name.strip()
            issue_object.normalized_key = normalize_issue_object_name(display_name)
        if object_type is not None:
            issue_object.object_type = object_type
        if code is not None:
            issue_object.code = code
        if is_active is not None:
            issue_object.is_active = is_active
        await self.session.flush()
        await self.session.refresh(issue_object)
        return issue_object

    async def soft_delete_issue_object(self, issue_object_id: int, user_id: UUID) -> None:
        issue_object = await self.get_by_id(issue_object_id)
        if not issue_object:
            raise ValueError(f"IssueObject {issue_object_id} not found")
        if issue_object.deleted_at is not None:
            raise ValueError(f"IssueObject {issue_object_id} already deleted")
        if issue_object.is_active:
            raise ValueError(f"Cannot delete active issue_object {issue_object_id}")
        issue_object.deleted_at = datetime.now()
        issue_object.deleted_by_user_id = user_id
        await self.session.flush()

    async def list_issue_objects_with_filters(
        self,
        *,
        search: str | None = None,
        object_type: str | None = None,
        include_inactive: bool = False,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IssueObject], int]:
        stmt = select(IssueObject).where(IssueObject.merged_into_id.is_(None))

        if not include_deleted:
            stmt = stmt.where(IssueObject.deleted_at.is_(None))
        if not include_inactive:
            stmt = stmt.where(IssueObject.is_active.is_(True))

        if search:
            search_term = f"%{search.lower()}%"
            stmt = stmt.where(
                or_(
                    IssueObject.display_name.ilike(search_term),
                    IssueObject.normalized_key.ilike(search_term),
                    IssueObject.code.ilike(search_term) if IssueObject.code is not None else false(),
                )
            )

        if object_type:
            stmt = stmt.where(IssueObject.object_type == object_type)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = (await self.session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(IssueObject.display_name).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), int(total_count)
