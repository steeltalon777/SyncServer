from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession



from app.models.category import Category
from app.models.item import Item
from app.models.unit import Unit

class CatalogRepo:
    """Read-only catalog access for incremental sync."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_items(self, updated_after: datetime | None, limit: int) -> list[Item]:
        stmt = select(Item)

        if updated_after is not None:
            stmt = stmt.where(Item.updated_at > updated_after)

        stmt = stmt.order_by(Item.updated_at).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_categories(self, updated_after: datetime | None, limit: int) -> list[Category]:
        stmt = select(Category)

        if updated_after is not None:
            stmt = stmt.where(Category.updated_at > updated_after)

        stmt = stmt.order_by(Category.updated_at).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_units(self, updated_after: datetime | None, limit: int) -> list[Unit]:
        stmt = select(Unit)

        if updated_after is not None:
            stmt = stmt.where(Unit.updated_at > updated_after)

        stmt = stmt.order_by(Unit.updated_at).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_categories(self) -> list[Category]:
        stmt = select(Category).order_by(Category.sort_order, Category.name)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def build_category_tree(self, categories: list[Category]) -> list[dict]:
        nodes: dict[UUID, dict] = {}
        roots: list[dict] = []

        for category in categories:
            nodes[category.id] = {
                "id": category.id,
                "name": category.name,
                "code": category.code,
                "parent_id": category.parent_id,
                "is_active": category.is_active,
                "created_at": category.created_at,
                "updated_at": category.updated_at,
                "sort_order": category.sort_order,
                "path": [],
                "children": [],
            }

        for category in categories:
            node = nodes[category.id]

            if category.parent_id is not None and category.parent_id in nodes:
                parent = nodes[category.parent_id]
                parent["children"].append(node)
            else:
                roots.append(node)

        def sort_children(node: dict) -> None:
            node["children"].sort(
                key=lambda x: (x["sort_order"] is None, x["sort_order"], x["name"])
            )
            for child in node["children"]:
                sort_children(child)

        for root in roots:
            sort_children(root)

        return roots

    def build_paths(
        self,
        nodes: list[dict],
        parent_path: list[str] | None = None,
    ) -> None:
        if parent_path is None:
            parent_path = []

        for node in nodes:
            node["path"] = parent_path + [node["name"]]
            self.build_paths(node["children"], node["path"])

    async def get_categories_tree(self) -> list[dict]:
        categories = await self.get_all_categories()
        tree = self.build_category_tree(categories)
        self.build_paths(tree)
        return tree