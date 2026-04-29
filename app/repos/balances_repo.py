from datetime import UTC, datetime
from decimal import Decimal

from app.models.balance import Balance
from app.models.category import Category
from app.models.inventory_subject import InventorySubject
from app.models.item import Item
from app.models.site import Site
from app.models.temporary_item import TemporaryItem
from app.models.unit import Unit
from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


class BalancesRepo:
    """Balance rows access with row-level locking support."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_update(self, site_id: int, inventory_subject_id: int) -> Balance | None:
        stmt = (
            select(Balance)
            .where(and_(Balance.site_id == site_id, Balance.inventory_subject_id == inventory_subject_id))
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        site_id: int,
        inventory_subject_id: int,
        delta_qty: Decimal,
    ) -> Balance:
        balance = await self.get_for_update(site_id=site_id, inventory_subject_id=inventory_subject_id)

        if balance is None:
            # Получаем item_id из inventory_subject
            stmt = select(InventorySubject.item_id).where(InventorySubject.id == inventory_subject_id)
            result = await self.session.execute(stmt)
            item_id = result.scalar_one_or_none()

            balance = Balance(
                site_id=site_id,
                inventory_subject_id=inventory_subject_id,
                item_id=item_id,
                qty=delta_qty,
            )
            self.session.add(balance)
        else:
            balance.qty = balance.qty + delta_qty
            balance.updated_at = datetime.now(UTC)

        await self.session.flush()
        return balance

    async def update_balance_quantity(
        self,
        site_id: int,
        inventory_subject_id: int,
        quantity_delta: Decimal,
    ) -> Balance:
        return await self.upsert(
            site_id=site_id,
            inventory_subject_id=inventory_subject_id,
            delta_qty=quantity_delta,
        )

    async def get_all_by_inventory_subject(self, inventory_subject_id: int) -> list[Balance]:
        """Get all balance rows for a given inventory_subject_id (across all sites)."""
        stmt = select(Balance).where(Balance.inventory_subject_id == inventory_subject_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_balances(
        self,
        filter,
        user_site_ids: list[int],
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        stmt = (
            select(
                Balance.site_id.label("site_id"),
                Site.name.label("site_name"),
                Balance.inventory_subject_id.label("inventory_subject_id"),
                InventorySubject.subject_type.label("subject_type"),
                InventorySubject.item_id.label("item_id"),
                InventorySubject.temporary_item_id.label("temporary_item_id"),
                TemporaryItem.resolved_item_id.label("resolved_item_id"),
                Item.name.label("resolved_item_name"),
                func.coalesce(TemporaryItem.name, Item.name).label("display_name"),
                Item.name.label("item_name"),
                Item.sku.label("sku"),
                Item.unit_id.label("unit_id"),
                Unit.symbol.label("unit_symbol"),
                Item.category_id.label("category_id"),
                Category.name.label("category_name"),
                Balance.qty.label("qty"),
                Balance.updated_at.label("updated_at"),
            )
            .select_from(Balance)
            .join(Site, Site.id == Balance.site_id)
            .join(InventorySubject, InventorySubject.id == Balance.inventory_subject_id)
            .outerjoin(Item, Item.id == InventorySubject.item_id)
            .outerjoin(TemporaryItem, TemporaryItem.id == InventorySubject.temporary_item_id)
            .outerjoin(Category, Category.id == Item.category_id)
            .outerjoin(Unit, Unit.id == Item.unit_id)
            .where(Balance.site_id.in_(user_site_ids))
        )

        if filter.site_id is not None:
            stmt = stmt.where(Balance.site_id == filter.site_id)

        if filter.item_id is not None:
            stmt = stmt.where(InventorySubject.item_id == filter.item_id)

        if filter.inventory_subject_id is not None:
            stmt = stmt.where(Balance.inventory_subject_id == filter.inventory_subject_id)

        if filter.category_id is not None:
            stmt = stmt.where(Item.category_id == filter.category_id)

        if filter.search:
            search_value = filter.search.strip()
            term = f"%{search_value.lstrip('#')}%"
            stmt = stmt.where(
                or_(
                    Item.name.ilike(term),
                    Item.sku.ilike(term),
                    Category.name.ilike(term),
                    cast(Item.hashtags, String).ilike(term),
                    TemporaryItem.name.ilike(term),
                    TemporaryItem.sku.ilike(term),
                    cast(TemporaryItem.hashtags, String).ilike(term),
                    Site.name.ilike(term),
                )
            )

        if filter.only_positive:
            stmt = stmt.where(Balance.qty > 0)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            stmt.order_by(Balance.updated_at.desc(), Site.name, Item.name, InventorySubject.item_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        rows = (await self.session.execute(stmt)).all()
        return [dict(row._mapping) for row in rows], int(total_count)

    async def get_balances_summary(self, user_site_ids: list[int]) -> dict:
        stmt = select(
            func.count().label("rows_count"),
            func.count(func.distinct(Balance.site_id)).label("sites_count"),
            func.coalesce(func.sum(Balance.qty), 0).label("total_quantity"),
        ).where(Balance.site_id.in_(user_site_ids))

        row = (await self.session.execute(stmt)).one()

        return {
            "rows_count": int(row.rows_count or 0),
            "sites_count": int(row.sites_count or 0),
            "total_quantity": float(row.total_quantity or 0),
        }
