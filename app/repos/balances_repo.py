from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.balance import Balance
from app.models.category import Category
from app.models.item import Item
from app.models.site import Site
from app.models.unit import Unit


class BalancesRepo:
    """Balance rows access with row-level locking support."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_update(self, site_id: int, item_id: int) -> Balance | None:
        stmt = (
            select(Balance)
            .where(and_(Balance.site_id == site_id, Balance.item_id == item_id))
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(self, site_id: int, item_id: int, delta_qty: Decimal) -> Balance:
        balance = await self.get_for_update(site_id=site_id, item_id=item_id)

        if balance is None:
            balance = Balance(site_id=site_id, item_id=item_id, qty=delta_qty)
            self.session.add(balance)
        else:
            balance.qty = balance.qty + delta_qty
            balance.updated_at = datetime.now(UTC)

        await self.session.flush()
        return balance

    async def update_balance_quantity(
        self,
        site_id: int,
        item_id: int,
        quantity_delta: Decimal,
    ) -> Balance:
        return await self.upsert(
            site_id=site_id,
            item_id=item_id,
            delta_qty=quantity_delta,
        )

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
                Balance.item_id.label("item_id"),
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
            .join(Item, Item.id == Balance.item_id)
            .join(Category, Category.id == Item.category_id)
            .join(Unit, Unit.id == Item.unit_id)
            .where(Balance.site_id.in_(user_site_ids))
        )

        if filter.site_id is not None:
            stmt = stmt.where(Balance.site_id == filter.site_id)

        if filter.item_id is not None:
            stmt = stmt.where(Balance.item_id == filter.item_id)

        if filter.category_id is not None:
            stmt = stmt.where(Item.category_id == filter.category_id)

        if filter.search:
            term = f"%{filter.search.strip()}%"
            stmt = stmt.where(
                or_(
                    Item.name.ilike(term),
                    Item.sku.ilike(term),
                    Category.name.ilike(term),
                    Site.name.ilike(term),
                )
            )

        if filter.only_positive:
            stmt = stmt.where(Balance.qty > 0)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            stmt.order_by(Balance.updated_at.desc(), Site.name, Item.name, Balance.item_id)
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
