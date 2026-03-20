from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.category import Category
from app.models.item import Item
from app.models.unit import Unit


class CatalogRepo:
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

    async def list_items_page(
        self,
        *,
        search: str | None,
        category_id: int | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        stmt = (
            select(
                Item.id.label("id"),
                Item.sku.label("sku"),
                Item.name.label("name"),
                Item.category_id.label("category_id"),
                Category.name.label("category_name"),
                Item.unit_id.label("unit_id"),
                Unit.symbol.label("unit_symbol"),
                Item.description.label("description"),
                Item.is_active.label("is_active"),
                Item.updated_at.label("updated_at"),
            )
            .join(Category, Category.id == Item.category_id)
            .join(Unit, Unit.id == Item.unit_id)
            .where(
                Item.is_active.is_(True),
                Category.is_active.is_(True),
                Unit.is_active.is_(True),
            )
        )

        if category_id is not None:
            stmt = stmt.where(Item.category_id == category_id)

        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Item.name.ilike(term),
                    Item.sku.ilike(term),
                    Item.description.ilike(term),
                )
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            stmt.order_by(Item.name, Item.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        rows = (await self.session.execute(stmt)).all()
        return [dict(row._mapping) for row in rows], int(total_count)

    async def list_categories_page(
        self,
        *,
        search: str | None,
        parent_id: int | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        parent = aliased(Category)
        item_counts = (
            select(
                Item.category_id.label("category_id"),
                func.count(Item.id).label("items_count"),
            )
            .where(Item.is_active.is_(True))
            .group_by(Item.category_id)
            .subquery()
        )
        child_counts = (
            select(
                Category.parent_id.label("parent_id"),
                func.count(Category.id).label("children_count"),
            )
            .where(
                Category.is_active.is_(True),
                Category.parent_id.is_not(None),
            )
            .group_by(Category.parent_id)
            .subquery()
        )

        stmt = (
            select(
                Category.id.label("id"),
                Category.name.label("name"),
                Category.code.label("code"),
                Category.parent_id.label("parent_id"),
                Category.is_active.label("is_active"),
                Category.updated_at.label("updated_at"),
                Category.sort_order.label("sort_order"),
                parent.id.label("parent_ref_id"),
                parent.name.label("parent_name"),
                func.coalesce(item_counts.c.items_count, 0).label("items_count"),
                func.coalesce(child_counts.c.children_count, 0).label("children_count"),
            )
            .select_from(Category)
            .outerjoin(parent, Category.parent_id == parent.id)
            .outerjoin(item_counts, item_counts.c.category_id == Category.id)
            .outerjoin(child_counts, child_counts.c.parent_id == Category.id)
            .where(Category.is_active.is_(True))
        )

        if parent_id is not None:
            stmt = stmt.where(Category.parent_id == parent_id)

        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Category.name.ilike(term),
                    Category.code.ilike(term),
                )
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            stmt.order_by(
                Category.sort_order.is_(None),
                Category.sort_order,
                Category.name,
                Category.id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        rows = (await self.session.execute(stmt)).all()
        return [dict(row._mapping) for row in rows], int(total_count)

    async def list_categories_by_ids(self, category_ids: list[int]) -> list[Category]:
        if not category_ids:
            return []
        stmt = select(Category).where(Category.id.in_(category_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_items_preview(
        self,
        category_ids: list[int],
        limit_per_category: int,
    ) -> dict[int, list[dict]]:
        if not category_ids:
            return {}

        ranked_items = (
            select(
                Item.id.label("id"),
                Item.name.label("name"),
                Item.category_id.label("category_id"),
                func.row_number().over(
                    partition_by=Item.category_id,
                    order_by=(Item.name, Item.id),
                ).label("row_number"),
            )
            .where(
                Item.category_id.in_(category_ids),
                Item.is_active.is_(True),
            )
            .subquery()
        )
        stmt = (
            select(
                ranked_items.c.id,
                ranked_items.c.name,
                ranked_items.c.category_id,
            )
            .where(ranked_items.c.row_number <= limit_per_category)
            .order_by(
                ranked_items.c.category_id,
                ranked_items.c.name,
                ranked_items.c.id,
            )
        )

        rows = (await self.session.execute(stmt)).all()
        preview_by_category: dict[int, list[dict]] = {category_id: [] for category_id in category_ids}
        for row in rows:
            preview_by_category[int(row.category_id)].append(
                {
                    "id": int(row.id),
                    "name": row.name,
                }
            )
        return preview_by_category

    async def get_parent_chain_summaries(
        self,
        category_ids: list[int],
    ) -> dict[int, list[dict]]:
        if not category_ids:
            return {}

        requested_categories = await self.list_categories_by_ids(category_ids)
        category_by_id = {category.id: category for category in requested_categories}
        pending_ids = {
            category.parent_id
            for category in requested_categories
            if category.parent_id is not None
        }

        while pending_ids:
            missing_ids = [category_id for category_id in pending_ids if category_id not in category_by_id]
            if not missing_ids:
                break
            parents = await self.list_categories_by_ids(missing_ids)
            if not parents:
                break
            for parent in parents:
                category_by_id[parent.id] = parent
            pending_ids = {
                parent.parent_id
                for parent in parents
                if parent.parent_id is not None and parent.parent_id not in category_by_id
            }

        chains: dict[int, list[dict]] = {}
        for category in requested_categories:
            chain: list[dict] = []
            current_parent_id = category.parent_id
            seen_ids: set[int] = set()
            while current_parent_id is not None and current_parent_id not in seen_ids:
                seen_ids.add(current_parent_id)
                parent = category_by_id.get(current_parent_id)
                if parent is None:
                    break
                chain.append({"id": parent.id, "name": parent.name})
                current_parent_id = parent.parent_id
            chain.reverse()
            chains[category.id] = chain
        return chains

    async def get_all_categories(self) -> list[Category]:
        stmt = select(Category).order_by(Category.sort_order, Category.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_unit(self, unit: Unit) -> Unit:
        self.session.add(unit)
        await self.session.flush()
        await self.session.refresh(unit)
        return unit

    async def get_unit_by_id(self, unit_id: int) -> Unit | None:
        result = await self.session.execute(select(Unit).where(Unit.id == unit_id))
        return result.scalar_one_or_none()

    async def get_unit_by_name(self, name: str) -> Unit | None:
        result = await self.session.execute(select(Unit).where(Unit.name == name))
        return result.scalar_one_or_none()

    async def get_unit_by_symbol(self, symbol: str) -> Unit | None:
        result = await self.session.execute(select(Unit).where(Unit.symbol == symbol))
        return result.scalar_one_or_none()

    async def update_unit(self, unit: Unit) -> Unit:
        await self.session.flush()
        await self.session.refresh(unit)
        return unit

    async def create_category(self, category: Category) -> Category:
        self.session.add(category)
        await self.session.flush()
        await self.session.refresh(category)
        return category

    async def get_category_by_id(self, category_id: int) -> Category | None:
        result = await self.session.execute(select(Category).where(Category.id == category_id))
        return result.scalar_one_or_none()

    async def get_category_by_parent_and_name(self, parent_id: int | None, name: str) -> Category | None:
        stmt = select(Category).where(Category.parent_id == parent_id, Category.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_categories_by_code(self, code: str) -> list[Category]:
        result = await self.session.execute(select(Category).where(Category.code == code))
        return list(result.scalars().all())

    async def update_category(self, category: Category) -> Category:
        await self.session.flush()
        await self.session.refresh(category)
        return category

    async def list_category_ancestors(self, category_id: int) -> set[int]:
        ancestors: set[int] = set()
        current = await self.get_category_by_id(category_id)

        while current is not None and current.parent_id is not None:
            if current.parent_id in ancestors:
                break
            ancestors.add(current.parent_id)
            current = await self.get_category_by_id(current.parent_id)

        return ancestors

    async def create_item(self, item: Item) -> Item:
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def get_item_by_id(self, item_id: int) -> Item | None:
        result = await self.session.execute(select(Item).where(Item.id == item_id))
        return result.scalar_one_or_none()

    async def get_item_by_sku(self, sku: str) -> Item | None:
        result = await self.session.execute(select(Item).where(Item.sku == sku))
        return result.scalar_one_or_none()

    async def update_item(self, item: Item) -> Item:
        await self.session.flush()
        await self.session.refresh(item)
        return item

    def build_category_tree(self, categories: list[Category]) -> list[dict]:
        nodes: dict[int, dict] = {}
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
            node["children"].sort(key=lambda x: (x["sort_order"] is None, x["sort_order"], x["name"]))
            for child in node["children"]:
                sort_children(child)

        for root in roots:
            sort_children(root)

        return roots

    def build_paths(self, nodes: list[dict], parent_path: list[str] | None = None) -> None:
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
