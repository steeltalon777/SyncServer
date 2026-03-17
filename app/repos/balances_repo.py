from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.balance import Balance


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
    ) -> tuple[list[Balance], int]:
        stmt = select(Balance).where(Balance.site_id.in_(user_site_ids))

        if filter.site_id is not None:
            stmt = stmt.where(Balance.site_id == filter.site_id)

        if filter.item_id is not None:
            stmt = stmt.where(Balance.item_id == filter.item_id)

        if filter.only_positive:
            stmt = stmt.where(Balance.qty > 0)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            stmt.order_by(Balance.updated_at.desc(), Balance.site_id, Balance.item_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total_count

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
