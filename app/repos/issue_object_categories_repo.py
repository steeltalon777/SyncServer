from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.issue_object import IssueObject
from app.models.issue_object_category import IssueObjectCategory

_NON_WORD_RE = re.compile(r"[^\w\s]+", flags=re.UNICODE)
_SPACES_RE = re.compile(r"\s+", flags=re.UNICODE)


def normalize_category_name(value: str) -> str:
    text = (value or "").strip().lower().replace("ё", "е")
    text = _NON_WORD_RE.sub(" ", text)
    text = _SPACES_RE.sub(" ", text).strip()
    return text


class IssueObjectCategoriesRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, category_id: int) -> IssueObjectCategory | None:
        return await self.session.get(IssueObjectCategory, category_id)

    async def list_categories(
        self,
        *,
        search: str | None = None,
        parent_id: int | None = None,
        is_active: bool | None = None,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IssueObjectCategory], int]:
        stmt = select(IssueObjectCategory)
        count_stmt = select(func.count()).select_from(IssueObjectCategory)

        if not include_deleted:
            stmt = stmt.where(IssueObjectCategory.deleted_at.is_(None))
            count_stmt = count_stmt.where(IssueObjectCategory.deleted_at.is_(None))

        if is_active is not None:
            stmt = stmt.where(IssueObjectCategory.is_active.is_(is_active))
            count_stmt = count_stmt.where(IssueObjectCategory.is_active.is_(is_active))

        if parent_id is not None:
            stmt = stmt.where(IssueObjectCategory.parent_id == parent_id)
            count_stmt = count_stmt.where(IssueObjectCategory.parent_id == parent_id)
        else:
            stmt = stmt.where(IssueObjectCategory.parent_id.is_(None))
            count_stmt = count_stmt.where(IssueObjectCategory.parent_id.is_(None))

        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    IssueObjectCategory.name.ilike(term),
                    IssueObjectCategory.normalized_key.ilike(term),
                )
            )
            count_stmt = count_stmt.where(
                or_(
                    IssueObjectCategory.name.ilike(term),
                    IssueObjectCategory.normalized_key.ilike(term),
                )
            )

        total_count = (await self.session.execute(count_stmt)).scalar_one()
        stmt = (
            stmt.order_by(IssueObjectCategory.sort_order, IssueObjectCategory.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        categories = list((await self.session.execute(stmt)).scalars().all())
        return categories, int(total_count)

    async def create_category(
        self,
        *,
        name: str,
        normalized_key: str,
        parent_id: int | None = None,
        sort_order: int = 0,
        is_active: bool = True,
    ) -> IssueObjectCategory:
        category = IssueObjectCategory(
            name=name.strip(),
            normalized_key=normalized_key,
            parent_id=parent_id,
            sort_order=sort_order,
            is_active=is_active,
        )
        self.session.add(category)
        await self.session.flush()
        await self.session.refresh(category)
        return category

    async def update_category(
        self,
        category_id: int,
        *,
        name: str | None = None,
        normalized_key: str | None = None,
        parent_id: int | None = None,
        sort_order: int | None = None,
        is_active: bool | None = None,
    ) -> IssueObjectCategory:
        category = await self.get_by_id(category_id)
        if not category:
            raise ValueError(f"IssueObjectCategory {category_id} not found")
        if category.deleted_at is not None:
            raise ValueError(f"IssueObjectCategory {category_id} is deleted")
        if name is not None:
            category.name = name.strip()
            if normalized_key is not None:
                category.normalized_key = normalized_key
            else:
                category.normalized_key = normalize_category_name(name)
        if parent_id is not None:
            category.parent_id = parent_id
        if sort_order is not None:
            category.sort_order = sort_order
        if is_active is not None:
            category.is_active = is_active
        await self.session.flush()
        await self.session.refresh(category)
        return category

    async def soft_delete_category(self, category_id: int, user_id: UUID) -> None:
        category = await self.get_by_id(category_id)
        if not category:
            raise ValueError(f"IssueObjectCategory {category_id} not found")
        if category.deleted_at is not None:
            raise ValueError(f"IssueObjectCategory {category_id} already deleted")
        category.deleted_at = datetime.now()
        category.deleted_by_user_id = user_id
        await self.session.flush()

    async def get_children(self, category_id: int) -> list[IssueObjectCategory]:
        stmt = (
            select(IssueObjectCategory)
            .where(
                and_(
                    IssueObjectCategory.parent_id == category_id,
                    IssueObjectCategory.deleted_at.is_(None),
                )
            )
            .order_by(IssueObjectCategory.sort_order, IssueObjectCategory.name)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_children_filtered(
        self,
        category_id: int,
        *,
        include_inactive: bool = False,
        include_deleted: bool = False,
    ) -> list[IssueObjectCategory]:
        stmt = select(IssueObjectCategory).where(IssueObjectCategory.parent_id == category_id)
        if not include_deleted:
            stmt = stmt.where(IssueObjectCategory.deleted_at.is_(None))
        if not include_inactive:
            stmt = stmt.where(IssueObjectCategory.is_active.is_(True))
        stmt = stmt.order_by(IssueObjectCategory.sort_order, IssueObjectCategory.name)
        return list((await self.session.execute(stmt)).scalars().all())

    async def has_active_children(self, category_id: int) -> bool:
        stmt = select(func.count()).select_from(IssueObjectCategory).where(
            and_(
                IssueObjectCategory.parent_id == category_id,
                IssueObjectCategory.deleted_at.is_(None),
                IssueObjectCategory.is_active.is_(True),
            )
        )
        count = (await self.session.execute(stmt)).scalar_one()
        return int(count) > 0

    async def has_active_objects(self, category_id: int) -> bool:
        stmt = select(func.count()).select_from(IssueObject).where(
            and_(
                IssueObject.category_id == category_id,
                IssueObject.deleted_at.is_(None),
                IssueObject.is_active.is_(True),
            )
        )
        count = (await self.session.execute(stmt)).scalar_one()
        return int(count) > 0

    async def get_by_parent_and_normalized_key(
        self, parent_id: int | None, normalized_key: str
    ) -> IssueObjectCategory | None:
        stmt = select(IssueObjectCategory).where(
            IssueObjectCategory.parent_id == parent_id,
            IssueObjectCategory.normalized_key == normalized_key,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_objects_for_category(self, category_id: int) -> list[IssueObject]:
        stmt = (
            select(IssueObject)
            .where(
                and_(
                    IssueObject.category_id == category_id,
                    IssueObject.deleted_at.is_(None),
                    IssueObject.is_active.is_(True),
                    IssueObject.merged_into_id.is_(None),
                )
            )
            .order_by(IssueObject.display_name)
        )
        return list((await self.session.execute(stmt)).scalars().all())
