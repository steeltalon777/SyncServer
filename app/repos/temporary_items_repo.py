from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.temporary_item import TemporaryItem


class TemporaryItemsRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        item_id: int,
        name: str,
        normalized_name: str,
        sku: str | None,
        unit_id: int,
        category_id: int,
        description: str | None,
        hashtags: list[str] | None,
        created_by_user_id: UUID,
    ) -> TemporaryItem:
        entity = TemporaryItem(
            item_id=item_id,
            name=name,
            normalized_name=normalized_name,
            sku=sku,
            unit_id=unit_id,
            category_id=category_id,
            description=description,
            hashtags=hashtags or [],
            status="active",
            created_by_user_id=created_by_user_id,
        )
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get_by_id(self, temporary_item_id: int) -> TemporaryItem | None:
        stmt = (
            select(TemporaryItem)
            .where(TemporaryItem.id == temporary_item_id)
            .options(
                selectinload(TemporaryItem.item),
                selectinload(TemporaryItem.resolved_item),
                selectinload(TemporaryItem.unit),
                selectinload(TemporaryItem.category),
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_item_id(self, item_id: int) -> TemporaryItem | None:
        stmt = select(TemporaryItem).where(TemporaryItem.item_id == item_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_items(
        self,
        *,
        status: str | None,
        search: str | None,
        created_by_user_id: UUID | None,
        resolved_item_id: int | None,
        created_after: datetime | None,
        created_before: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[TemporaryItem], int]:
        stmt: Select[tuple[TemporaryItem]] = select(TemporaryItem).options(
            selectinload(TemporaryItem.item),
            selectinload(TemporaryItem.resolved_item),
            selectinload(TemporaryItem.unit),
            selectinload(TemporaryItem.category),
        )
        if status is not None:
            stmt = stmt.where(TemporaryItem.status == status)
        if created_by_user_id is not None:
            stmt = stmt.where(TemporaryItem.created_by_user_id == created_by_user_id)
        if resolved_item_id is not None:
            stmt = stmt.where(TemporaryItem.resolved_item_id == resolved_item_id)
        if created_after is not None:
            stmt = stmt.where(TemporaryItem.created_at >= created_after)
        if created_before is not None:
            stmt = stmt.where(TemporaryItem.created_at <= created_before)
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    TemporaryItem.name.ilike(term),
                    TemporaryItem.sku.ilike(term),
                    TemporaryItem.description.ilike(term),
                )
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = int((await self.session.execute(count_stmt)).scalar_one())
        stmt = stmt.order_by(TemporaryItem.created_at.desc(), TemporaryItem.id.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        items = list((await self.session.execute(stmt)).scalars().all())
        return items, total_count

    async def resolve_as_item(
        self,
        *,
        temporary_item_id: int,
        resolved_item_id: int,
        resolved_by_user_id: UUID,
        resolution_type: str,
        resolution_note: str | None,
    ) -> TemporaryItem | None:
        entity = await self.get_by_id(temporary_item_id)
        if entity is None:
            return None
        entity.status = "approved_as_item"
        entity.resolved_item_id = resolved_item_id
        entity.resolution_type = resolution_type
        entity.resolution_note = resolution_note
        entity.resolved_by_user_id = resolved_by_user_id
        entity.resolved_at = datetime.now(UTC)
        await self.session.flush()
        return entity

    async def merge_to_item(
        self,
        *,
        temporary_item_id: int,
        target_item_id: int,
        resolved_by_user_id: UUID,
        resolution_note: str | None,
    ) -> TemporaryItem | None:
        entity = await self.get_by_id(temporary_item_id)
        if entity is None:
            return None
        entity.status = "merged_to_item"
        entity.resolved_item_id = target_item_id
        entity.resolution_type = "merge"
        entity.resolution_note = resolution_note
        entity.resolved_by_user_id = resolved_by_user_id
        entity.resolved_at = datetime.now(UTC)
        if entity.item is not None:
            entity.item.is_active = False
        await self.session.flush()
        return entity

    async def mark_deleted(
        self,
        *,
        temporary_item_id: int,
        resolved_by_user_id: UUID,
        resolution_note: str | None,
    ) -> TemporaryItem | None:
        """Пометить временный ТМЦ как удалённый (мягкое удаление)."""
        entity = await self.get_by_id(temporary_item_id)
        if entity is None:
            return None
        entity.status = "deleted"
        entity.resolution_type = "deleted"
        entity.resolution_note = resolution_note
        entity.resolved_by_user_id = resolved_by_user_id
        entity.resolved_at = datetime.now(UTC)
        if entity.item is not None:
            entity.item.is_active = False
        await self.session.flush()
        return entity
