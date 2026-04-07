from __future__ import annotations

from sqlalchemy import case, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.balance import Balance
from app.models.category import Category
from app.models.item import Item
from app.models.operation import Operation, OperationLine
from app.models.site import Site
from app.models.unit import Unit


class ReportsRepo:
    """Reporting/read-model queries for dashboard and document generation."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_item_movement(
        self,
        *,
        filter,
        user_site_ids: list[int],
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        operation_at = func.coalesce(Operation.effective_at, Operation.created_at)

        receive_rows = (
            select(
                Operation.site_id.label("site_id"),
                OperationLine.item_id.label("item_id"),
                operation_at.label("operation_at"),
                OperationLine.qty.label("delta_qty"),
            )
            .select_from(Operation)
            .join(OperationLine, OperationLine.operation_id == Operation.id)
            .where(Operation.status == "submitted")
            .where(Operation.operation_type == "RECEIVE")
        )

        decrement_rows = (
            select(
                Operation.site_id.label("site_id"),
                OperationLine.item_id.label("item_id"),
                operation_at.label("operation_at"),
                (-OperationLine.qty).label("delta_qty"),
            )
            .select_from(Operation)
            .join(OperationLine, OperationLine.operation_id == Operation.id)
            .where(Operation.status == "submitted")
            .where(Operation.operation_type.in_(("EXPENSE", "WRITE_OFF")))
        )

        adjustment_rows = (
            select(
                Operation.site_id.label("site_id"),
                OperationLine.item_id.label("item_id"),
                operation_at.label("operation_at"),
                OperationLine.qty.label("delta_qty"),
            )
            .select_from(Operation)
            .join(OperationLine, OperationLine.operation_id == Operation.id)
            .where(Operation.status == "submitted")
            .where(Operation.operation_type == "ADJUSTMENT")
        )

        move_out_rows = (
            select(
                Operation.source_site_id.label("site_id"),
                OperationLine.item_id.label("item_id"),
                operation_at.label("operation_at"),
                (-OperationLine.qty).label("delta_qty"),
            )
            .select_from(Operation)
            .join(OperationLine, OperationLine.operation_id == Operation.id)
            .where(Operation.status == "submitted")
            .where(Operation.operation_type == "MOVE")
            .where(Operation.source_site_id.is_not(None))
        )

        move_in_rows = (
            select(
                Operation.destination_site_id.label("site_id"),
                OperationLine.item_id.label("item_id"),
                operation_at.label("operation_at"),
                OperationLine.qty.label("delta_qty"),
            )
            .select_from(Operation)
            .join(OperationLine, OperationLine.operation_id == Operation.id)
            .where(Operation.status == "submitted")
            .where(Operation.operation_type == "MOVE")
            .where(Operation.destination_site_id.is_not(None))
        )

        movement_rows = union_all(
            receive_rows,
            decrement_rows,
            adjustment_rows,
            move_out_rows,
            move_in_rows,
        ).subquery()

        base_stmt = (
            select(
                movement_rows.c.site_id.label("site_id"),
                Site.name.label("site_name"),
                movement_rows.c.item_id.label("item_id"),
                Item.name.label("item_name"),
                Item.sku.label("sku"),
                Item.unit_id.label("unit_id"),
                Unit.symbol.label("unit_symbol"),
                Item.category_id.label("category_id"),
                Category.name.label("category_name"),
                func.coalesce(
                    func.sum(
                        case(
                            (movement_rows.c.delta_qty > 0, movement_rows.c.delta_qty),
                            else_=literal(0),
                        )
                    ),
                    0,
                ).label("incoming_qty"),
                func.coalesce(
                    func.sum(
                        case(
                            (movement_rows.c.delta_qty < 0, func.abs(movement_rows.c.delta_qty)),
                            else_=literal(0),
                        )
                    ),
                    0,
                ).label("outgoing_qty"),
                func.coalesce(func.sum(movement_rows.c.delta_qty), 0).label("net_qty"),
                func.max(movement_rows.c.operation_at).label("last_operation_at"),
            )
            .select_from(movement_rows)
            .join(Site, Site.id == movement_rows.c.site_id)
            .join(Item, Item.id == movement_rows.c.item_id)
            .join(Category, Category.id == Item.category_id)
            .join(Unit, Unit.id == Item.unit_id)
            .where(movement_rows.c.site_id.in_(user_site_ids))
        )

        if filter.site_id is not None:
            base_stmt = base_stmt.where(movement_rows.c.site_id == filter.site_id)

        if filter.item_id is not None:
            base_stmt = base_stmt.where(movement_rows.c.item_id == filter.item_id)

        if filter.category_id is not None:
            base_stmt = base_stmt.where(Item.category_id == filter.category_id)

        if filter.date_from is not None:
            base_stmt = base_stmt.where(movement_rows.c.operation_at >= filter.date_from)

        if filter.date_to is not None:
            base_stmt = base_stmt.where(movement_rows.c.operation_at <= filter.date_to)

        if filter.search:
            term = f"%{filter.search.strip()}%"
            base_stmt = base_stmt.where(
                or_(
                    Item.name.ilike(term),
                    Item.sku.ilike(term),
                    Category.name.ilike(term),
                    Site.name.ilike(term),
                )
            )

        base_stmt = base_stmt.group_by(
            movement_rows.c.site_id,
            Site.name,
            movement_rows.c.item_id,
            Item.name,
            Item.sku,
            Item.unit_id,
            Unit.symbol,
            Item.category_id,
            Category.name,
        )

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_count = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            base_stmt.order_by(
                func.max(movement_rows.c.operation_at).desc(),
                Site.name,
                Item.name,
                movement_rows.c.item_id,
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        rows = (await self.session.execute(stmt)).all()
        return [dict(row._mapping) for row in rows], int(total_count)

    async def list_stock_summary(
        self,
        *,
        filter,
        user_site_ids: list[int],
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        base_stmt = (
            select(
                Balance.site_id.label("site_id"),
                Site.name.label("site_name"),
                func.count().label("items_count"),
                func.coalesce(
                    func.sum(
                        case(
                            (Balance.qty > 0, literal(1)),
                            else_=literal(0),
                        )
                    ),
                    0,
                ).label("positive_items_count"),
                func.coalesce(func.sum(Balance.qty), 0).label("total_quantity"),
                func.max(Balance.updated_at).label("last_balance_at"),
            )
            .select_from(Balance)
            .join(Site, Site.id == Balance.site_id)
            .join(Item, Item.id == Balance.item_id)
            .join(Category, Category.id == Item.category_id)
            .where(Balance.site_id.in_(user_site_ids))
        )

        if filter.site_id is not None:
            base_stmt = base_stmt.where(Balance.site_id == filter.site_id)

        if filter.category_id is not None:
            base_stmt = base_stmt.where(Item.category_id == filter.category_id)

        if filter.only_positive:
            base_stmt = base_stmt.where(Balance.qty > 0)

        if filter.search:
            term = f"%{filter.search.strip()}%"
            base_stmt = base_stmt.where(
                or_(
                    Item.name.ilike(term),
                    Item.sku.ilike(term),
                    Category.name.ilike(term),
                    Site.name.ilike(term),
                )
            )

        base_stmt = base_stmt.group_by(Balance.site_id, Site.name)

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_count = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            base_stmt.order_by(Site.name, Balance.site_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        rows = (await self.session.execute(stmt)).all()
        return [dict(row._mapping) for row in rows], int(total_count)
