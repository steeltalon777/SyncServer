from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.balance import Balance


class BalancesRepo:
    """Balance rows access with row-level locking support."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_update(self, site_id: UUID, item_id: UUID) -> Balance | None:
        stmt = select(Balance).where(and_(Balance.site_id == site_id, Balance.item_id == item_id)).with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(self, site_id: UUID, item_id: UUID, delta_qty: Decimal) -> Balance:
        balance = await self.get_for_update(site_id=site_id, item_id=item_id)

        if balance is None:
            balance = Balance(site_id=site_id, item_id=item_id, qty=delta_qty)
            self.session.add(balance)
        else:
            balance.qty = balance.qty + delta_qty
            balance.updated_at = datetime.now(UTC)

        await self.session.flush()
        return balance
