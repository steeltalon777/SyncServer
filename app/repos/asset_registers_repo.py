from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_register import (
    IssuedAssetBalance,
    LostAssetBalance,
    OperationAcceptanceAction,
    PendingAcceptanceBalance,
)
from app.models.item import Item
from app.models.recipient import Recipient
from app.models.site import Site


class AssetRegistersRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_pending_for_update(self, operation_line_id: int) -> PendingAcceptanceBalance | None:
        stmt = (
            select(PendingAcceptanceBalance)
            .where(PendingAcceptanceBalance.operation_line_id == operation_line_id)
            .with_for_update()
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _get_lost_for_update(self, operation_line_id: int) -> LostAssetBalance | None:
        stmt = (
            select(LostAssetBalance)
            .where(LostAssetBalance.operation_line_id == operation_line_id)
            .with_for_update()
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _get_issued_for_update(self, recipient_id: int, item_id: int) -> IssuedAssetBalance | None:
        stmt = (
            select(IssuedAssetBalance)
            .where(
                and_(
                    IssuedAssetBalance.recipient_id == recipient_id,
                    IssuedAssetBalance.item_id == item_id,
                )
            )
            .with_for_update()
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert_pending(
        self,
        *,
        operation_id: UUID,
        operation_line_id: int,
        destination_site_id: int,
        source_site_id: int | None,
        item_id: int,
        qty_delta: Decimal,
    ) -> PendingAcceptanceBalance | None:
        row = await self._get_pending_for_update(operation_line_id)
        if row is None:
            if qty_delta < 0:
                raise ValueError("insufficient pending quantity")
            if qty_delta == 0:
                return None
            row = PendingAcceptanceBalance(
                operation_line_id=operation_line_id,
                operation_id=operation_id,
                destination_site_id=destination_site_id,
                source_site_id=source_site_id,
                item_id=item_id,
                qty=qty_delta,
            )
            self.session.add(row)
            await self.session.flush()
            return row

        next_qty = Decimal(row.qty) + qty_delta
        if next_qty < 0:
            raise ValueError("insufficient pending quantity")
        if next_qty == 0:
            await self.session.delete(row)
            await self.session.flush()
            return None

        row.qty = next_qty
        row.updated_at = datetime.now(UTC)
        await self.session.flush()
        return row

    async def upsert_lost(
        self,
        *,
        operation_id: UUID,
        operation_line_id: int,
        site_id: int,
        source_site_id: int | None,
        item_id: int,
        qty_delta: Decimal,
    ) -> LostAssetBalance | None:
        row = await self._get_lost_for_update(operation_line_id)
        if row is None:
            if qty_delta < 0:
                raise ValueError("insufficient lost quantity")
            if qty_delta == 0:
                return None
            row = LostAssetBalance(
                operation_line_id=operation_line_id,
                operation_id=operation_id,
                site_id=site_id,
                source_site_id=source_site_id,
                item_id=item_id,
                qty=qty_delta,
            )
            self.session.add(row)
            await self.session.flush()
            return row

        next_qty = Decimal(row.qty) + qty_delta
        if next_qty < 0:
            raise ValueError("insufficient lost quantity")
        if next_qty == 0:
            await self.session.delete(row)
            await self.session.flush()
            return None

        row.qty = next_qty
        row.updated_at = datetime.now(UTC)
        await self.session.flush()
        return row

    async def upsert_issued(
        self,
        *,
        recipient_id: int,
        item_id: int,
        qty_delta: Decimal,
    ) -> IssuedAssetBalance | None:
        row = await self._get_issued_for_update(recipient_id, item_id)
        if row is None:
            if qty_delta < 0:
                raise ValueError("insufficient issued quantity")
            if qty_delta == 0:
                return None
            row = IssuedAssetBalance(
                recipient_id=recipient_id,
                item_id=item_id,
                qty=qty_delta,
            )
            self.session.add(row)
            await self.session.flush()
            return row

        next_qty = Decimal(row.qty) + qty_delta
        if next_qty < 0:
            raise ValueError("insufficient issued quantity")
        if next_qty == 0:
            await self.session.delete(row)
            await self.session.flush()
            return None

        row.qty = next_qty
        row.updated_at = datetime.now(UTC)
        await self.session.flush()
        return row

    async def list_pending(
        self,
        *,
        user_site_ids: list[int],
        site_id: int | None,
        operation_id: UUID | None,
        item_id: int | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        stmt = (
            select(
                PendingAcceptanceBalance.operation_id.label("operation_id"),
                PendingAcceptanceBalance.operation_line_id.label("operation_line_id"),
                PendingAcceptanceBalance.destination_site_id.label("destination_site_id"),
                Site.name.label("destination_site_name"),
                PendingAcceptanceBalance.source_site_id.label("source_site_id"),
                PendingAcceptanceBalance.item_id.label("item_id"),
                Item.name.label("item_name"),
                Item.sku.label("sku"),
                PendingAcceptanceBalance.qty.label("qty"),
                PendingAcceptanceBalance.updated_at.label("updated_at"),
            )
            .select_from(PendingAcceptanceBalance)
            .join(Site, Site.id == PendingAcceptanceBalance.destination_site_id)
            .join(Item, Item.id == PendingAcceptanceBalance.item_id)
            .where(PendingAcceptanceBalance.destination_site_id.in_(user_site_ids))
        )

        if site_id is not None:
            stmt = stmt.where(PendingAcceptanceBalance.destination_site_id == site_id)
        if operation_id is not None:
            stmt = stmt.where(PendingAcceptanceBalance.operation_id == operation_id)
        if item_id is not None:
            stmt = stmt.where(PendingAcceptanceBalance.item_id == item_id)
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(or_(Item.name.ilike(term), Item.sku.ilike(term), Site.name.ilike(term)))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            stmt.order_by(PendingAcceptanceBalance.updated_at.desc(), PendingAcceptanceBalance.operation_line_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(stmt)).all()
        return [dict(row._mapping) for row in rows], int(total_count)

    async def list_lost(
        self,
        *,
        user_site_ids: list[int],
        site_id: int | None,
        source_site_id: int | None,
        operation_id: UUID | None,
        item_id: int | None,
        search: str | None,
        updated_after: datetime | None = None,
        updated_before: datetime | None = None,
        qty_from: Decimal | None = None,
        qty_to: Decimal | None = None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        destination = Site
        source = Site.__table__.alias("source_site")

        stmt = (
            select(
                LostAssetBalance.operation_id.label("operation_id"),
                LostAssetBalance.operation_line_id.label("operation_line_id"),
                LostAssetBalance.site_id.label("site_id"),
                destination.name.label("site_name"),
                LostAssetBalance.source_site_id.label("source_site_id"),
                source.c.name.label("source_site_name"),
                LostAssetBalance.item_id.label("item_id"),
                Item.name.label("item_name"),
                Item.sku.label("sku"),
                LostAssetBalance.qty.label("qty"),
                LostAssetBalance.updated_at.label("updated_at"),
            )
            .select_from(LostAssetBalance)
            .join(destination, destination.id == LostAssetBalance.site_id)
            .join(Item, Item.id == LostAssetBalance.item_id)
            .outerjoin(source, source.c.id == LostAssetBalance.source_site_id)
            .where(LostAssetBalance.site_id.in_(user_site_ids))
        )

        if site_id is not None:
            stmt = stmt.where(LostAssetBalance.site_id == site_id)
        if source_site_id is not None:
            stmt = stmt.where(LostAssetBalance.source_site_id == source_site_id)
        if operation_id is not None:
            stmt = stmt.where(LostAssetBalance.operation_id == operation_id)
        if item_id is not None:
            stmt = stmt.where(LostAssetBalance.item_id == item_id)
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Item.name.ilike(term),
                    Item.sku.ilike(term),
                    destination.name.ilike(term),
                    source.c.name.ilike(term),
                )
            )
        if updated_after is not None:
            stmt = stmt.where(LostAssetBalance.updated_at >= updated_after)
        if updated_before is not None:
            stmt = stmt.where(LostAssetBalance.updated_at <= updated_before)
        if qty_from is not None:
            stmt = stmt.where(LostAssetBalance.qty >= qty_from)
        if qty_to is not None:
            stmt = stmt.where(LostAssetBalance.qty <= qty_to)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = (await self.session.execute(count_stmt)).scalar_one()
        stmt = (
            stmt.order_by(LostAssetBalance.updated_at.desc(), LostAssetBalance.operation_line_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(stmt)).all()
        return [dict(row._mapping) for row in rows], int(total_count)

    async def list_issued(
        self,
        *,
        recipient_id: int | None,
        item_id: int | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        stmt = (
            select(
                IssuedAssetBalance.recipient_id.label("recipient_id"),
                Recipient.display_name.label("recipient_name"),
                Recipient.recipient_type.label("recipient_type"),
                IssuedAssetBalance.item_id.label("item_id"),
                Item.name.label("item_name"),
                Item.sku.label("sku"),
                IssuedAssetBalance.qty.label("qty"),
                IssuedAssetBalance.updated_at.label("updated_at"),
            )
            .select_from(IssuedAssetBalance)
            .join(Recipient, Recipient.id == IssuedAssetBalance.recipient_id)
            .join(Item, Item.id == IssuedAssetBalance.item_id)
        )

        if recipient_id is not None:
            stmt = stmt.where(IssuedAssetBalance.recipient_id == recipient_id)
        if item_id is not None:
            stmt = stmt.where(IssuedAssetBalance.item_id == item_id)
        if search:
            term = f"%{search.strip()}%"
            stmt = stmt.where(or_(Recipient.display_name.ilike(term), Item.name.ilike(term), Item.sku.ilike(term)))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = (await self.session.execute(count_stmt)).scalar_one()
        stmt = (
            stmt.order_by(IssuedAssetBalance.updated_at.desc(), IssuedAssetBalance.recipient_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(stmt)).all()
        return [dict(row._mapping) for row in rows], int(total_count)

    async def get_pending_rows_by_operation(self, operation_id: UUID) -> list[PendingAcceptanceBalance]:
        stmt = select(PendingAcceptanceBalance).where(PendingAcceptanceBalance.operation_id == operation_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_lost_rows_by_operation(self, operation_id: UUID) -> list[LostAssetBalance]:
        stmt = select(LostAssetBalance).where(LostAssetBalance.operation_id == operation_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_lost_row_for_update(self, operation_line_id: int) -> LostAssetBalance | None:
        return await self._get_lost_for_update(operation_line_id)

    async def get_lost_row(self, operation_line_id: int) -> dict | None:
        """Retrieve a single lost asset row with joined site and item info."""
        destination = Site
        source = Site.__table__.alias("source_site")
        stmt = (
            select(
                LostAssetBalance.operation_id.label("operation_id"),
                LostAssetBalance.operation_line_id.label("operation_line_id"),
                LostAssetBalance.site_id.label("site_id"),
                destination.name.label("site_name"),
                LostAssetBalance.source_site_id.label("source_site_id"),
                source.c.name.label("source_site_name"),
                LostAssetBalance.item_id.label("item_id"),
                Item.name.label("item_name"),
                Item.sku.label("sku"),
                LostAssetBalance.qty.label("qty"),
                LostAssetBalance.updated_at.label("updated_at"),
            )
            .select_from(LostAssetBalance)
            .join(destination, destination.id == LostAssetBalance.site_id)
            .join(Item, Item.id == LostAssetBalance.item_id)
            .outerjoin(source, source.c.id == LostAssetBalance.source_site_id)
            .where(LostAssetBalance.operation_line_id == operation_line_id)
        )
        result = (await self.session.execute(stmt)).first()
        if result is None:
            return None
        return dict(result._mapping)

    async def create_acceptance_action(
        self,
        *,
        operation_id: UUID,
        operation_line_id: int,
        action_type: str,
        qty: Decimal,
        performed_by_user_id: UUID,
        recipient_id: int | None = None,
        notes: str | None = None,
    ) -> OperationAcceptanceAction:
        action = OperationAcceptanceAction(
            operation_id=operation_id,
            operation_line_id=operation_line_id,
            action_type=action_type,
            qty=qty,
            performed_by_user_id=performed_by_user_id,
            recipient_id=recipient_id,
            notes=notes,
        )
        self.session.add(action)
        await self.session.flush()
        return action
