from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.item import Item


class CatalogRepo:
    """Read-only catalog access for incremental sync."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_items(self, updated_after: datetime | None, limit: int) -> list[Item]:
        stmt = select(Item).order_by(Item.updated_at).limit(limit)
        if updated_after is not None:
            stmt = stmt.where(Item.updated_at > updated_after)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_categories(self, updated_after: datetime | None, limit: int) -> list[Category]:
        stmt = select(Category).order_by(Category.updated_at).limit(limit)
        if updated_after is not None:
            stmt = stmt.where(Category.updated_at > updated_after)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
