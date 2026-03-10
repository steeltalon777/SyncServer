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

    async def get_all_categories(self)  -> list[Category]:
        stmt = select(Category)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def build_category_tree(self, categories: list[Category]) -> list[dict]:
        nodes: dict = {}
        roots:list = []

        # узлы
        for c in categories:
            nodes[c.id] = {
                "id": c.id,
                "name": c.name,
                "code": c.code,
                "parent_id": c.parent_id,
                "is_active": c.is_active,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
                "sort_order": c.sort_order,
                "path": [],
                "children": [],
            }

        # делаем дерево
        for c in categories:
            node = nodes[c.id]

            if c.parent_id and c.parent_id in nodes:
                parent = nodes[c.parent_id]
                parent["children"].append(node)
            else:
                roots.append(node)
        # сортировка детей
        def sort_children(node):
            node["children"].sort(
                key=lambda x: (x["sort_order"] is None, x["sort_order"], x["name"])
            )
            for child in node["children"]:
                sort_children(child)

        for r in roots:
            sort_children(r)

        return roots

    def build_paths(self, nodes: list[dict], parent_path: list[str] | None = None):

        if parent_path is None:
            parent_path = []

        for node in nodes:
            node["path"] = parent_path + [node["name"]]
            self.build_paths(node["children"], node["path"])

    async def get_categories_tree(self):

        categories = await self.get_all_categories()

        tree = self.build_category_tree(categories)

        self.build_paths(tree)

        return tree
