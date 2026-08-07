from __future__ import annotations

from sqlalchemy import case, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.balance import Balance
from app.models.category import Category
from app.models.inventory_subject import InventorySubject
from app.models.item import Item
from app.models.operation import Operation, OperationLine
from app.models.site import Site
from app.models.temporary_item import TemporaryItem
from app.models.unit import Unit
from app.core.search_utils import build_normalized_like_term, build_raw_like_term


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
        exclude_system_effects: bool = True,
    ) -> tuple[list[dict], int]:
        operation_at = func.coalesce(Operation.effective_at, Operation.created_at)

        # A-6 (ADR-0028 §7): exclude system-generated operations (origin='system')
        # per UNION branch, before aggregation. Manual/legacy operations (origin
        # 'user' or NULL) are retained regardless of operation type.
        system_origin_filter = func.coalesce(Operation.origin, "user") != "system"
        accepted_or_full_qty = case(
            (Operation.acceptance_required.is_(True), OperationLine.accepted_qty),
            else_=OperationLine.qty,
        )

        receive_rows = (
            select(
                Operation.site_id.label("site_id"),
                OperationLine.inventory_subject_id.label("inventory_subject_id"),
                OperationLine.item_id.label("item_id"),
                operation_at.label("operation_at"),
                accepted_or_full_qty.label("delta_qty"),
            )
            .select_from(Operation)
            .join(OperationLine, OperationLine.operation_id == Operation.id)
            .where(Operation.status == "submitted")
            .where(Operation.operation_type == "RECEIVE")
        )
        if exclude_system_effects:
            receive_rows = receive_rows.where(system_origin_filter)

        decrement_rows = (
            select(
                Operation.site_id.label("site_id"),
                OperationLine.inventory_subject_id.label("inventory_subject_id"),
                OperationLine.item_id.label("item_id"),
                operation_at.label("operation_at"),
                (-OperationLine.qty).label("delta_qty"),
            )
            .select_from(Operation)
            .join(OperationLine, OperationLine.operation_id == Operation.id)
            .where(Operation.status == "submitted")
            .where(Operation.operation_type.in_(("EXPENSE", "WRITE_OFF")))
        )
        if exclude_system_effects:
            decrement_rows = decrement_rows.where(system_origin_filter)

        adjustment_rows = (
            select(
                Operation.site_id.label("site_id"),
                OperationLine.inventory_subject_id.label("inventory_subject_id"),
                OperationLine.item_id.label("item_id"),
                operation_at.label("operation_at"),
                OperationLine.qty.label("delta_qty"),
            )
            .select_from(Operation)
            .join(OperationLine, OperationLine.operation_id == Operation.id)
            .where(Operation.status == "submitted")
            .where(Operation.operation_type == "ADJUSTMENT")
        )
        if exclude_system_effects:
            adjustment_rows = adjustment_rows.where(system_origin_filter)

        move_out_rows = (
            select(
                Operation.source_site_id.label("site_id"),
                OperationLine.inventory_subject_id.label("inventory_subject_id"),
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
        if exclude_system_effects:
            move_out_rows = move_out_rows.where(system_origin_filter)

        move_in_rows = (
            select(
                Operation.destination_site_id.label("site_id"),
                OperationLine.inventory_subject_id.label("inventory_subject_id"),
                OperationLine.item_id.label("item_id"),
                operation_at.label("operation_at"),
                accepted_or_full_qty.label("delta_qty"),
            )
            .select_from(Operation)
            .join(OperationLine, OperationLine.operation_id == Operation.id)
            .where(Operation.status == "submitted")
            .where(Operation.operation_type == "MOVE")
            .where(Operation.destination_site_id.is_not(None))
        )
        if exclude_system_effects:
            move_in_rows = move_in_rows.where(system_origin_filter)

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
                movement_rows.c.inventory_subject_id.label("inventory_subject_id"),
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
            .join(InventorySubject, InventorySubject.id == movement_rows.c.inventory_subject_id)
            .outerjoin(Item, Item.id == InventorySubject.item_id)
            .outerjoin(TemporaryItem, TemporaryItem.id == InventorySubject.temporary_item_id)
            .outerjoin(Category, Category.id == Item.category_id)
            .outerjoin(Unit, Unit.id == Item.unit_id)
            .where(movement_rows.c.site_id.in_(user_site_ids))
        )

        if filter.site_id is not None:
            base_stmt = base_stmt.where(movement_rows.c.site_id == filter.site_id)

        if filter.item_id is not None:
            base_stmt = base_stmt.where(InventorySubject.item_id == filter.item_id)

        if filter.category_id is not None:
            base_stmt = base_stmt.where(Item.category_id == filter.category_id)

        if filter.date_from is not None:
            base_stmt = base_stmt.where(movement_rows.c.operation_at >= filter.date_from)

        if filter.date_to is not None:
            base_stmt = base_stmt.where(movement_rows.c.operation_at <= filter.date_to)

        if filter.search:
            normalized_term = build_normalized_like_term(filter.search)
            raw_term = build_raw_like_term(filter.search)
            conditions = []
            if normalized_term is not None:
                conditions.append(Item.normalized_name.ilike(normalized_term, escape="\\"))
                conditions.append(Category.normalized_name.ilike(normalized_term, escape="\\"))
                conditions.append(Site.normalized_name.ilike(normalized_term, escape="\\"))
            if raw_term is not None:
                conditions.append(Item.sku.ilike(raw_term, escape="\\"))
            if conditions:
                base_stmt = base_stmt.where(or_(*conditions))

        base_stmt = base_stmt.group_by(
            movement_rows.c.site_id,
            Site.name,
            movement_rows.c.inventory_subject_id,
            InventorySubject.subject_type,
            InventorySubject.item_id,
            InventorySubject.temporary_item_id,
            TemporaryItem.resolved_item_id,
            TemporaryItem.name,
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
                InventorySubject.item_id,
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
                Balance.inventory_subject_id.label("inventory_subject_id"),
                InventorySubject.subject_type.label("subject_type"),
                InventorySubject.item_id.label("item_id"),
                InventorySubject.temporary_item_id.label("temporary_item_id"),
                TemporaryItem.resolved_item_id.label("resolved_item_id"),
                Item.name.label("resolved_item_name"),
                func.coalesce(TemporaryItem.name, Item.name).label("display_name"),
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
            .join(InventorySubject, InventorySubject.id == Balance.inventory_subject_id)
            .outerjoin(Item, Item.id == InventorySubject.item_id)
            .outerjoin(TemporaryItem, TemporaryItem.id == InventorySubject.temporary_item_id)
            .outerjoin(Category, Category.id == Item.category_id)
            .where(Balance.site_id.in_(user_site_ids))
        )

        if filter.site_id is not None:
            base_stmt = base_stmt.where(Balance.site_id == filter.site_id)

        if filter.category_id is not None:
            base_stmt = base_stmt.where(Item.category_id == filter.category_id)

        if filter.only_positive:
            base_stmt = base_stmt.where(Balance.qty > 0)

        if filter.search:
            normalized_term = build_normalized_like_term(filter.search)
            raw_term = build_raw_like_term(filter.search)
            conditions = []
            if normalized_term is not None:
                conditions.append(Item.normalized_name.ilike(normalized_term, escape="\\"))
                conditions.append(Category.normalized_name.ilike(normalized_term, escape="\\"))
                conditions.append(Site.normalized_name.ilike(normalized_term, escape="\\"))
            if raw_term is not None:
                conditions.append(Item.sku.ilike(raw_term, escape="\\"))
            if conditions:
                base_stmt = base_stmt.where(or_(*conditions))

        base_stmt = base_stmt.group_by(
            Balance.site_id,
            Site.name,
            Balance.inventory_subject_id,
            InventorySubject.subject_type,
            InventorySubject.item_id,
            InventorySubject.temporary_item_id,
            TemporaryItem.resolved_item_id,
            Item.name,
            TemporaryItem.name,
        )

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_count = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            base_stmt.order_by(Site.name, Balance.site_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        rows = (await self.session.execute(stmt)).all()
        return [dict(row._mapping) for row in rows], int(total_count)
