from __future__ import annotations

import inspect
import structlog
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.core.catalog_defaults import (
    UNCATEGORIZED_CATEGORY_CODE,
    UNCATEGORIZED_CATEGORY_NAME,
)
from app.models.category import Category
from app.models.item import Item
from app.models.unit import Unit
from app.schemas.catalog import (
    CategoryBulkCreateRequest,
    CategoryCreateRequest,
    CategoryUpdateRequest,
    ItemCreateRequest,
    ItemUpdateRequest,
    UnitBulkCreateRequest,
    UnitCreateRequest,
    UnitUpdateRequest,
    CatalogBatchRequest,
    BatchChangeCreate,
    BatchChangeUpdate,
    BatchChangeDeactivate,
    BatchChangeDelete,
    BatchChangeResult,
    BatchChangeUnitPayload,
    BatchChangeCategoryPayload,
    BatchChangeItemPayload,
    BatchChangeUpdatePayload,
)
from fastapi import HTTPException, status

from app.services.uow import UnitOfWork

logger = structlog.get_logger()


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.strip().lower().split())


class CatalogAdminService:
    async def create_unit(self, uow: UnitOfWork, payload: UnitCreateRequest, created_by_user_id: UUID | None = None) -> Unit:
        await self._ensure_unit_unique(uow, name=payload.name, symbol=payload.symbol)

        unit = Unit(
            code=payload.symbol.upper(),
            name=payload.name,
            symbol=payload.symbol,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
        )
        if created_by_user_id is not None:
            unit.created_by_user_id = created_by_user_id
        return await uow.catalog.create_unit(unit)

    async def bulk_create_units(self, uow: UnitOfWork, payload: UnitBulkCreateRequest, created_by_user_id: UUID | None = None) -> list[Unit]:
        seen_names: set[str] = set()
        seen_symbols: set[str] = set()
        for item in payload.items:
            normalized_name = _normalize_text(item.name)
            normalized_symbol = _normalize_text(item.symbol)
            if normalized_name in seen_names:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="duplicate unit name in payload")
            if normalized_symbol in seen_symbols:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="duplicate unit symbol in payload")
            seen_names.add(normalized_name)
            seen_symbols.add(normalized_symbol)

        created: list[Unit] = []
        for item in payload.items:
            unit = await self.create_unit(uow, item, created_by_user_id=created_by_user_id)
            created.append(unit)
        return created

    async def update_unit(self, uow: UnitOfWork, unit_id: int, payload: UnitUpdateRequest, updated_by_user_id: UUID | None = None) -> Unit:
        unit = await uow.catalog.get_unit_by_id(unit_id)
        if unit is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unit not found")

        if payload.name is not None and payload.name != unit.name:
            existing = await uow.catalog.get_unit_by_name(payload.name)
            if existing is not None and existing.id != unit.id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="unit name already exists")
            unit.name = payload.name

        if payload.symbol is not None and payload.symbol != unit.symbol:
            existing = await uow.catalog.get_unit_by_symbol(payload.symbol)
            if existing is not None and existing.id != unit.id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="unit symbol already exists")
            previous_symbol = unit.symbol
            unit.symbol = payload.symbol
            if unit.code is None or unit.code == previous_symbol.upper():
                unit.code = payload.symbol.upper()

        if payload.sort_order is not None:
            unit.sort_order = payload.sort_order
        if payload.is_active is not None:
            unit.is_active = payload.is_active

        if updated_by_user_id is not None:
            unit.updated_by_user_id = updated_by_user_id
        return await uow.catalog.update_unit(unit)

    async def create_category(self, uow: UnitOfWork, payload: CategoryCreateRequest, created_by_user_id: UUID | None = None) -> Category:
        if payload.code == UNCATEGORIZED_CATEGORY_CODE:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="reserved category code")

        if payload.parent_id is not None:
            parent = await uow.catalog.get_category_by_id(payload.parent_id)
            if parent is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="parent category not found")

        sibling = await uow.catalog.get_category_by_parent_and_name(payload.parent_id, payload.name)
        if sibling is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="category name already exists for parent")

        category = Category(
            name=payload.name,
            normalized_name=_normalize_text(payload.name),
            code=payload.code,
            parent_id=payload.parent_id,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
        )
        if created_by_user_id is not None:
            category.created_by_user_id = created_by_user_id
        return await uow.catalog.create_category(category)

    async def bulk_create_categories(self, uow: UnitOfWork, payload: CategoryBulkCreateRequest, created_by_user_id: UUID | None = None) -> list[Category]:
        created: list[Category] = []
        for item in payload.items:
            category = await self.create_category(uow, item, created_by_user_id=created_by_user_id)
            created.append(category)
        return created

    async def update_category(self, uow: UnitOfWork, category_id: int, payload: CategoryUpdateRequest, updated_by_user_id: UUID | None = None) -> Category:
        category = await uow.catalog.get_category_by_id(category_id)
        if category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="category not found")
        if category.code == UNCATEGORIZED_CATEGORY_CODE:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="system category is read-only")
        if payload.code == UNCATEGORIZED_CATEGORY_CODE:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="reserved category code")

        parent_updated = "parent_id" in payload.model_fields_set
        target_parent_id = payload.parent_id if parent_updated else category.parent_id
        target_name = payload.name if payload.name is not None else category.name

        if target_parent_id == category.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="category parent_id cannot equal id")

        if parent_updated:
            if payload.parent_id is not None:
                parent = await uow.catalog.get_category_by_id(payload.parent_id)
                if parent is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="parent category not found")
                await self._validate_no_category_cycle(uow, category_id=category.id, new_parent_id=payload.parent_id)
            category.parent_id = payload.parent_id

        sibling = await uow.catalog.get_category_by_parent_and_name(target_parent_id, target_name)
        if sibling is not None and sibling.id != category.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="category name already exists for parent")

        if payload.name is not None:
            category.name = payload.name
            category.normalized_name = _normalize_text(payload.name)
        if "code" in payload.model_fields_set:
            category.code = payload.code
        if "sort_order" in payload.model_fields_set:
            category.sort_order = payload.sort_order
        if payload.is_active is not None:
            category.is_active = payload.is_active

        if updated_by_user_id is not None:
            category.updated_by_user_id = updated_by_user_id
        return await uow.catalog.update_category(category)

    async def create_item(self, uow: UnitOfWork, payload: ItemCreateRequest, created_by_user_id: UUID | None = None) -> Item:
        category = await self._resolve_item_category(uow, payload.category_id)
        await self._validate_unit_exists(uow, payload.unit_id)
        await self._ensure_item_sku_unique(uow, payload.sku)

        logger.info(
            "catalog_admin_create_item",
            repo_method=getattr(uow.catalog.create_item, "__qualname__", repr(uow.catalog.create_item)),
            repo_signature=str(inspect.signature(uow.catalog.create_item)),
            payload_name=payload.name,
            payload_sku=payload.sku,
            category_id=category.id,
            unit_id=payload.unit_id,
            hashtags_len=len(payload.hashtags or []),
            is_active=payload.is_active,
        )

        item = Item(
            sku=payload.sku,
            name=payload.name,
            normalized_name=_normalize_text(payload.name),
            category_id=category.id,
            unit_id=payload.unit_id,
            description=payload.description,
            hashtags=payload.hashtags,
            is_active=payload.is_active,
            requires_review=payload.requires_review,
            review_created_by_user_id=created_by_user_id if payload.requires_review else None,
            review_status="needs_review" if payload.requires_review else None,
            created_by_user_id=created_by_user_id,
        )
        return await uow.catalog.create_item(item)

    async def _assert_item_not_frozen(self, uow: UnitOfWork, item_id: int) -> None:
        if await uow.asset_registers.has_active_lost_for_item(item_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="item is frozen by active lost asset balance",
            )

    async def update_item(self, uow: UnitOfWork, item_id: int, payload: ItemUpdateRequest, updated_by_user_id: UUID | None = None) -> Item:
        item = await uow.catalog.get_item_by_id(item_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")
        await self._assert_item_not_frozen(uow, item_id)

        if "category_id" in payload.model_fields_set:
            category = await self._resolve_item_category(uow, payload.category_id)
            category_id = category.id
        else:
            category_id = item.category_id
        unit_id = payload.unit_id if payload.unit_id is not None else item.unit_id
        await self._validate_unit_exists(uow, unit_id)

        if payload.sku is not None and payload.sku != item.sku:
            existing = await uow.catalog.get_item_by_sku(payload.sku)
            if existing is not None and existing.id != item.id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="item sku already exists")
            item.sku = payload.sku

        if payload.name is not None:
            item.name = payload.name
            item.normalized_name = _normalize_text(payload.name)
        if "category_id" in payload.model_fields_set:
            item.category_id = category_id
        if payload.unit_id is not None:
            item.unit_id = payload.unit_id
        if "description" in payload.model_fields_set:
            item.description = payload.description
        if "hashtags" in payload.model_fields_set:
            item.hashtags = payload.hashtags
        if payload.is_active is not None:
            item.is_active = payload.is_active

        if updated_by_user_id is not None:
            item.updated_by_user_id = updated_by_user_id
        return await uow.catalog.update_item(item)

    async def _ensure_unit_unique(self, uow: UnitOfWork, name: str, symbol: str) -> None:
        if await uow.catalog.get_unit_by_name(name):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="unit name already exists")
        if await uow.catalog.get_unit_by_symbol(symbol):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="unit symbol already exists")

    async def _validate_no_category_cycle(self, uow: UnitOfWork, category_id: int, new_parent_id: int) -> None:
        ancestors = await uow.catalog.list_category_ancestors(new_parent_id)
        if category_id in ancestors:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="category cycle detected")

    async def _validate_unit_exists(self, uow: UnitOfWork, unit_id: int) -> None:
        if await uow.catalog.get_unit_by_id(unit_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unit not found")

    async def _resolve_item_category(self, uow: UnitOfWork, category_id: int | None) -> Category:
        if category_id is not None:
            category = await uow.catalog.get_category_by_id(category_id)
            if category is not None and category.is_active:
                return category
        return await self._get_or_create_uncategorized_category(uow)

    async def _get_or_create_uncategorized_category(self, uow: UnitOfWork) -> Category:
        categories = await uow.catalog.list_categories_by_code(UNCATEGORIZED_CATEGORY_CODE)
        if len(categories) > 1:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="multiple uncategorized categories configured",
            )
        if categories:
            category = categories[0]
            category.name = UNCATEGORIZED_CATEGORY_NAME
            category.parent_id = None
            category.is_active = True
            await uow.catalog.update_category(category)
            return category

        category = Category(
            name=UNCATEGORIZED_CATEGORY_NAME,
            normalized_name=_normalize_text(UNCATEGORIZED_CATEGORY_NAME),
            code=UNCATEGORIZED_CATEGORY_CODE,
            parent_id=None,
            sort_order=None,
            is_active=True,
        )
        return await uow.catalog.create_category(category)

    async def _ensure_item_sku_unique(self, uow: UnitOfWork, sku: str | None) -> None:
        if sku is None:
            return
        existing = await uow.catalog.get_item_by_sku(sku)
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="item sku already exists")

    async def get_unit(self, uow: UnitOfWork, unit_id: int) -> Unit:
        unit = await uow.catalog.get_unit_by_id(unit_id)
        if unit is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unit not found")
        return unit

    async def get_category(self, uow: UnitOfWork, category_id: int) -> Category:
        category = await uow.catalog.get_category_by_id(category_id)
        if category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="category not found")
        return category

    async def get_item(self, uow: UnitOfWork, item_id: int) -> Item:
        item = await uow.catalog.get_item_by_id(item_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")
        return item

    async def delete_unit(self, uow: UnitOfWork, unit_id: int, user_id: UUID) -> None:
        unit = await uow.catalog.get_unit_by_id(unit_id)
        if unit is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unit not found")
        if unit.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="unit already deleted")
        if unit.is_active:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="cannot delete active unit")
        try:
            await uow.catalog.soft_delete_unit(unit_id, user_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    async def delete_category(self, uow: UnitOfWork, category_id: int, user_id: UUID) -> None:
        category = await uow.catalog.get_category_by_id(category_id)
        if category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="category not found")
        if category.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="category already deleted")
        if category.is_active:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="cannot delete active category")
        try:
            await uow.catalog.soft_delete_category(category_id, user_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    async def delete_item(self, uow: UnitOfWork, item_id: int, user_id: UUID) -> None:
        item = await uow.catalog.get_item_by_id(item_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")
        await self._assert_item_not_frozen(uow, item_id)
        if item.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="item already deleted")
        if item.is_active and not item.requires_review:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="cannot delete active item")
        try:
            await uow.catalog.soft_delete_item(item_id, user_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    async def list_units(
        self,
        uow: UnitOfWork,
        *,
        include_inactive: bool = False,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Unit], int]:
        return await uow.catalog.list_units_with_filters(
            include_inactive=include_inactive,
            include_deleted=include_deleted,
            page=page,
            page_size=page_size,
        )

    async def list_categories(
        self,
        uow: UnitOfWork,
        *,
        include_inactive: bool = False,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Category], int]:
        return await uow.catalog.list_categories_with_filters(
            include_inactive=include_inactive,
            include_deleted=include_deleted,
            page=page,
            page_size=page_size,
        )

    async def list_items(
        self,
        uow: UnitOfWork,
        *,
        include_inactive: bool = False,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Item], int]:
        return await uow.catalog.list_items_with_filters(
            include_inactive=include_inactive,
            include_deleted=include_deleted,
            page=page,
            page_size=page_size,
        )

    # ─── Merge Operations ────────────────────────────────────────────

    async def merge_items(
        self,
        uow: UnitOfWork,
        *,
        source_item_id: int,
        target_item_id: int,
        comment: str | None = None,
        resolved_by_user_id: UUID,
    ) -> Item:
        """Merge source item into target item.

        Steps:
        1. Load source + target, validate existence and no self-merge.
        2. Check not deleted, target is active.
        3. Assert neither item is frozen (lost assets).
        4. Transfer balances via ADJUSTMENT operations (write-off source, receipt target).
        5. Update all operation lines referencing source to point to target.
        6. Archive source inventory subject.
        7. Deactivate source, set merge audit fields.
        """
        source = await uow.catalog.get_item_by_id(source_item_id)
        if source is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source item not found")

        target = await uow.catalog.get_item_by_id(target_item_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target item not found")

        if source_item_id == target_item_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="cannot merge item into itself",
            )

        if source.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source item is deleted")
        if target.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target item is deleted")
        if not target.is_active:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="target item is not active")

        await self._assert_item_not_frozen(uow, source_item_id)
        await self._assert_item_not_frozen(uow, target_item_id)

        # Get inventory subjects
        source_subject = await uow.inventory_subjects.get_by_item_id(source_item_id)
        target_subject = await uow.inventory_subjects.get_or_create_for_item(item_id=target_item_id)

        # Transfer balances via ADJUSTMENT operations
        if source_subject is not None and source_subject.archived_at is None:
            source_balances = await uow.balances.get_all_by_inventory_subject(int(source_subject.id))
            for balance_row in source_balances:
                qty = balance_row.qty
                if qty == 0:
                    continue

                site_id = int(balance_row.site_id)
                note = (
                    f"[catalog merge] item={source_item_id} -> item={target_item_id}: "
                    f"balance transfer site={site_id} qty={qty}"
                )

                # Write-off from source
                write_off = await uow.operations.create_operation(
                    site_id=site_id,
                    operation_type="ADJUSTMENT",
                    created_by_user_id=resolved_by_user_id,
                    notes=note,
                    effective_at=datetime.now(UTC),
                )
                await uow.operations.create_operation_line(
                    operation_id=write_off.id,
                    line_number=1,
                    inventory_subject_id=int(source_subject.id),
                    item_id=source_item_id,
                    qty=-Decimal(str(qty)),
                    comment=note,
                )
                from app.services.operations_service import OperationsService

                await OperationsService.submit_operation(
                    uow=uow,
                    operation_id=write_off.id,
                    user_id=resolved_by_user_id,
                )

                # Receipt to target
                receipt_op = await uow.operations.create_operation(
                    site_id=site_id,
                    operation_type="ADJUSTMENT",
                    created_by_user_id=resolved_by_user_id,
                    notes=note,
                    effective_at=datetime.now(UTC),
                )
                await uow.operations.create_operation_line(
                    operation_id=receipt_op.id,
                    line_number=1,
                    inventory_subject_id=int(target_subject.id),
                    item_id=target_item_id,
                    qty=Decimal(str(qty)),
                    comment=note,
                )
                await OperationsService.submit_operation(
                    uow=uow,
                    operation_id=receipt_op.id,
                    user_id=resolved_by_user_id,
                )

        # Update operation lines: all operation_lines referencing source → target
        from app.models.operation import OperationLine
        from sqlalchemy import update as sa_update

        await uow.session.execute(
            sa_update(OperationLine.__table__)
            .where(OperationLine.__table__.c.item_id == source_item_id)
            .values(item_id=target_item_id)
        )

        # Archive source inventory subject
        if source_subject is not None and source_subject.archived_at is None:
            await uow.inventory_subjects.archive(int(source_subject.id))

        # Deactivate source and set merge audit fields
        now = datetime.now(UTC)
        source.is_active = False
        source.merged_into_id = target_item_id
        source.merged_at = now
        source.merged_by_user_id = resolved_by_user_id
        source.merge_comment = comment

        await uow.catalog.update_item(source)

        logger.info(
            "merge_items",
            source_item_id=source_item_id,
            target_item_id=target_item_id,
            user_id=str(resolved_by_user_id),
        )

        return target

    async def merge_categories(
        self,
        uow: UnitOfWork,
        *,
        source_category_id: int,
        target_category_id: int,
        comment: str | None = None,
        resolved_by_user_id: UUID,
    ) -> Category:
        """Merge source category into target category.

        Steps:
        1. Load source + target, validate existence and no self-merge.
        2. Check not deleted, target is active.
        3. Check no cyclic dependency (target is not a descendant of source).
        4. Move all items from source category to target category.
        5. Move all subcategories from source to target.
        6. Deactivate source, set merge audit fields.
        """
        source = await uow.catalog.get_category_by_id(source_category_id)
        if source is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source category not found")

        target = await uow.catalog.get_category_by_id(target_category_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target category not found")

        if source_category_id == target_category_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="cannot merge category into itself",
            )

        if source.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source category is deleted")
        if target.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target category is deleted")
        if not target.is_active:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="target category is not active")

        # Check no cyclic dependency: target must not be a descendant of source
        ancestors = await uow.catalog.list_category_ancestors(target_category_id)
        if source_category_id in ancestors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="target category is a descendant of source category; would create cycle",
            )

        # Move all items from source category to target category
        from app.models.item import Item as ItemModel
        from app.models.category import Category as CategoryModel
        from sqlalchemy import update as sa_update

        await uow.session.execute(
            sa_update(ItemModel.__table__)
            .where(ItemModel.__table__.c.category_id == source_category_id)
            .where(ItemModel.__table__.c.deleted_at.is_(None))
            .values(category_id=target_category_id)
        )

        # Move all subcategories from source to target
        await uow.session.execute(
            sa_update(CategoryModel.__table__)
            .where(CategoryModel.__table__.c.parent_id == source_category_id)
            .where(CategoryModel.__table__.c.deleted_at.is_(None))
            .values(parent_id=target_category_id)
        )

        # Deactivate source and set merge audit fields
        now = datetime.now(UTC)
        source.is_active = False
        source.merged_into_id = target_category_id
        source.merged_at = now
        source.merged_by_user_id = resolved_by_user_id
        source.merge_comment = comment

        await uow.catalog.update_category(source)

        logger.info(
            "merge_categories",
            source_category_id=source_category_id,
            target_category_id=target_category_id,
            user_id=str(resolved_by_user_id),
        )

        return target

    # ─── Batch Catalog Operations ──────────────────────────────────────

    async def apply_batch(
        self,
        uow: UnitOfWork,
        payload: CatalogBatchRequest,
        identity: Identity,
    ) -> tuple[list[BatchChangeResult], dict[str, int]]:
        """
        Apply a mixed batch of catalog changes atomically.
        
        All changes are applied within a single UnitOfWork transaction.
        Any failure rolls back the entire batch.
        
        Args:
            uow: UnitOfWork instance for transactional operations
            payload: Batch request with changes to apply
            identity: User identity for permission checks and audit
            
        Returns:
            Tuple of (list of change results, summary counts)
            
        Raises:
            HTTPException: On validation or application failure
        """
        # Validate batch structure
        await self._validate_batch(payload)
        
        # Build local_id -> entity_id mapping for created entities
        local_id_map: dict[str, int] = {}
        results: list[BatchChangeResult] = []
        summary: dict[str, int] = {"create": 0, "update": 0, "deactivate": 0, "delete": 0, "error": 0}
        
        # Process changes in dependency order:
        # 1. Units (create/update/deactivate/delete)
        # 2. Categories (create in topological order, then update/deactivate/delete)
        # 3. Items (create/update/deactivate/delete)
        
        # Separate changes by entity type and action
        unit_creates = [c for c in payload.changes if c.entity_type == "unit" and c.action == "create"]
        unit_updates = [c for c in payload.changes if c.entity_type == "unit" and c.action == "update"]
        unit_deactivates = [c for c in payload.changes if c.entity_type == "unit" and c.action == "deactivate"]
        unit_deletes = [c for c in payload.changes if c.entity_type == "unit" and c.action == "delete"]
        
        category_creates = [c for c in payload.changes if c.entity_type == "category" and c.action == "create"]
        category_updates = [c for c in payload.changes if c.entity_type == "category" and c.action == "update"]
        category_deactivates = [c for c in payload.changes if c.entity_type == "category" and c.action == "deactivate"]
        category_deletes = [c for c in payload.changes if c.entity_type == "category" and c.action == "delete"]
        
        item_creates = [c for c in payload.changes if c.entity_type == "item" and c.action == "create"]
        item_updates = [c for c in payload.changes if c.entity_type == "item" and c.action == "update"]
        item_deactivates = [c for c in payload.changes if c.entity_type == "item" and c.action == "deactivate"]
        item_deletes = [c for c in payload.changes if c.entity_type == "item" and c.action == "delete"]
        
        # Sort category creates by parent dependencies (topological sort)
        sorted_category_creates = self._topological_sort_categories(category_creates)
        
        # Process units
        for change in unit_creates + unit_updates + unit_deactivates + unit_deletes:
            result = await self._apply_unit_change(uow, change, local_id_map, identity.user_id)
            results.append(result)
            if result.status == "applied":
                summary[change.action] += 1
                if change.action == "create" and result.entity_id:
                    local_id_map[change.local_id] = result.entity_id
            else:
                summary["error"] += 1
        
        # Process categories
        for change in sorted_category_creates + category_updates + category_deactivates + category_deletes:
            result = await self._apply_category_change(uow, change, local_id_map, identity.user_id)
            results.append(result)
            if result.status == "applied":
                summary[change.action] += 1
                if change.action == "create" and result.entity_id:
                    local_id_map[change.local_id] = result.entity_id
            else:
                summary["error"] += 1
        
        # Process items
        for change in item_creates + item_updates + item_deactivates + item_deletes:
            result = await self._apply_item_change(uow, change, local_id_map, identity.user_id)
            results.append(result)
            if result.status == "applied":
                summary[change.action] += 1
                if change.action == "create" and result.entity_id:
                    local_id_map[change.local_id] = result.entity_id
            else:
                summary["error"] += 1
        
        return results, summary

    async def _validate_batch(self, payload: CatalogBatchRequest) -> None:
        """Validate batch structure and local references."""
        # Check for duplicate local IDs (already done in schema)
        local_ids = {change.local_id for change in payload.changes}
        
        # Validate local references exist in batch
        for change in payload.changes:
            if isinstance(change, BatchChangeCreate):
                if change.entity_type == "category":
                    cat_payload = change.payload
                    if isinstance(cat_payload, BatchChangeCategoryPayload):
                        if cat_payload.parent_local_id and cat_payload.parent_local_id not in local_ids:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"parent_local_id {cat_payload.parent_local_id} not found in batch"
                            )
                elif change.entity_type == "item":
                    item_payload = change.payload
                    if isinstance(item_payload, BatchChangeItemPayload):
                        if item_payload.category_local_id and item_payload.category_local_id not in local_ids:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"category_local_id {item_payload.category_local_id} not found in batch"
                            )
                        if item_payload.unit_local_id and item_payload.unit_local_id not in local_ids:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"unit_local_id {item_payload.unit_local_id} not found in batch"
                            )
        
        # Validate no category cycles among new categories
        category_creates = [c for c in payload.changes if c.entity_type == "category" and c.action == "create"]
        if category_creates:
            self._validate_category_graph(category_creates)

    def _validate_category_graph(self, category_creates: list[BatchChangeCreate]) -> None:
        """Validate category parent graph for cycles and self-parent."""
        # Build adjacency: local_id -> parent_local_id
        parent_map: dict[str, str | None] = {}
        for change in category_creates:
            payload = change.payload
            if isinstance(payload, BatchChangeCategoryPayload):
                parent_map[change.local_id] = payload.parent_local_id
        
        # Check for self-parent
        for local_id, parent_id in parent_map.items():
            if parent_id == local_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Category {local_id} cannot be its own parent"
                )
        
        # Check for cycles using DFS
        visited: set[str] = set()
        rec_stack: set[str] = set()
        
        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            
            parent = parent_map.get(node)
            if parent and parent in parent_map:
                if parent not in visited:
                    if has_cycle(parent):
                        return True
                elif parent in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        for local_id in parent_map:
            if local_id not in visited:
                if has_cycle(local_id):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Category cycle detected in batch"
                    )

    def _topological_sort_categories(self, category_creates: list[BatchChangeCreate]) -> list[BatchChangeCreate]:
        """Sort category creates so parents come before children."""
        # Build adjacency: parent_local_id -> [child_local_ids]
        parent_map: dict[str, str | None] = {}
        for change in category_creates:
            payload = change.payload
            if isinstance(payload, BatchChangeCategoryPayload):
                parent_map[change.local_id] = payload.parent_local_id
        
        # Kahn's algorithm
        in_degree: dict[str, int] = {lid: 0 for lid in parent_map}
        for lid, parent in parent_map.items():
            if parent and parent in parent_map:
                in_degree[lid] = 1
        
        # Start with nodes that have no parent (or parent not in batch)
        queue = [lid for lid, deg in in_degree.items() if deg == 0]
        result: list[BatchChangeCreate] = []
        local_id_to_change = {c.local_id: c for c in category_creates}
        
        while queue:
            current = queue.pop(0)
            result.append(local_id_to_change[current])
            
            # Reduce in-degree for children
            for lid, parent in parent_map.items():
                if parent == current:
                    in_degree[lid] -= 1
                    if in_degree[lid] == 0:
                        queue.append(lid)
        
        return result

    async def _apply_unit_change(
        self,
        uow: UnitOfWork,
        change: BatchChangeCreate | BatchChangeUpdate | BatchChangeDeactivate | BatchChangeDelete,
        local_id_map: dict[str, int],
        user_id: UUID,
    ) -> BatchChangeResult:
        """Apply a single unit change."""
        try:
            if isinstance(change, BatchChangeCreate):
                payload = change.payload
                if isinstance(payload, BatchChangeUnitPayload):
                    unit = await self.create_unit(uow, payload, created_by_user_id=user_id)
                    return BatchChangeResult(
                        local_id=change.local_id,
                        entity_type="unit",
                        action="create",
                        status="applied",
                        entity_id=unit.id,
                    )
            elif isinstance(change, BatchChangeUpdate):
                payload = change.payload
                if isinstance(payload, BatchChangeUpdatePayload) and change.entity_id:
                    unit_payload = UnitUpdateRequest(
                        name=payload.name,
                        symbol=payload.symbol,
                        sort_order=payload.sort_order,
                        is_active=payload.is_active,
                    )
                    unit = await self.update_unit(uow, change.entity_id, unit_payload, updated_by_user_id=user_id)
                    return BatchChangeResult(
                        local_id=change.local_id,
                        entity_type="unit",
                        action="update",
                        status="applied",
                        entity_id=unit.id,
                    )
            elif isinstance(change, BatchChangeDeactivate):
                if change.entity_id:
                    unit_payload = UnitUpdateRequest(is_active=False)
                    unit = await self.update_unit(uow, change.entity_id, unit_payload, updated_by_user_id=user_id)
                    return BatchChangeResult(
                        local_id=change.local_id,
                        entity_type="unit",
                        action="deactivate",
                        status="applied",
                        entity_id=unit.id,
                    )
            elif isinstance(change, BatchChangeDelete):
                if change.entity_id:
                    await self.delete_unit(uow, change.entity_id, user_id)
                    return BatchChangeResult(
                        local_id=change.local_id,
                        entity_type="unit",
                        action="delete",
                        status="applied",
                        entity_id=change.entity_id,
                    )
        except HTTPException as e:
            return BatchChangeResult(
                local_id=change.local_id,
                entity_type="unit",
                action=change.action,
                status="error",
                error_code=e.detail if isinstance(e.detail, str) else "unknown_error",
                error_message=str(e.detail),
            )
        
        return BatchChangeResult(
            local_id=change.local_id,
            entity_type="unit",
            action=change.action,
            status="error",
            error_code="invalid_payload",
            error_message="Invalid payload for unit change",
        )

    async def _apply_category_change(
        self,
        uow: UnitOfWork,
        change: BatchChangeCreate | BatchChangeUpdate | BatchChangeDeactivate | BatchChangeDelete,
        local_id_map: dict[str, int],
        user_id: UUID,
    ) -> BatchChangeResult:
        """Apply a single category change."""
        try:
            if isinstance(change, BatchChangeCreate):
                payload = change.payload
                if isinstance(payload, BatchChangeCategoryPayload):
                    # Resolve parent_local_id if present
                    parent_id = payload.parent_id
                    if payload.parent_local_id and payload.parent_local_id in local_id_map:
                        parent_id = local_id_map[payload.parent_local_id]
                    
                    create_payload = CategoryCreateRequest(
                        name=payload.name,
                        code=payload.code,
                        parent_id=parent_id,
                        sort_order=payload.sort_order,
                        is_active=payload.is_active,
                    )
                    category = await self.create_category(uow, create_payload, created_by_user_id=user_id)
                    return BatchChangeResult(
                        local_id=change.local_id,
                        entity_type="category",
                        action="create",
                        status="applied",
                        entity_id=category.id,
                    )
            elif isinstance(change, BatchChangeUpdate):
                payload = change.payload
                if isinstance(payload, BatchChangeUpdatePayload) and change.entity_id:
                    category_payload = CategoryUpdateRequest(
                        name=payload.name,
                        code=payload.code,
                        parent_id=payload.parent_id,
                        sort_order=payload.sort_order,
                        is_active=payload.is_active,
                    )
                    category = await self.update_category(uow, change.entity_id, category_payload, updated_by_user_id=user_id)
                    return BatchChangeResult(
                        local_id=change.local_id,
                        entity_type="category",
                        action="update",
                        status="applied",
                        entity_id=category.id,
                    )
            elif isinstance(change, BatchChangeDeactivate):
                if change.entity_id:
                    category_payload = CategoryUpdateRequest(is_active=False)
                    category = await self.update_category(uow, change.entity_id, category_payload, updated_by_user_id=user_id)
                    return BatchChangeResult(
                        local_id=change.local_id,
                        entity_type="category",
                        action="deactivate",
                        status="applied",
                        entity_id=category.id,
                    )
            elif isinstance(change, BatchChangeDelete):
                if change.entity_id:
                    await self.delete_category(uow, change.entity_id, user_id)
                    return BatchChangeResult(
                        local_id=change.local_id,
                        entity_type="category",
                        action="delete",
                        status="applied",
                        entity_id=change.entity_id,
                    )
        except HTTPException as e:
            return BatchChangeResult(
                local_id=change.local_id,
                entity_type="category",
                action=change.action,
                status="error",
                error_code=e.detail if isinstance(e.detail, str) else "unknown_error",
                error_message=str(e.detail),
            )
        
        return BatchChangeResult(
            local_id=change.local_id,
            entity_type="category",
            action=change.action,
            status="error",
            error_code="invalid_payload",
            error_message="Invalid payload for category change",
        )

    async def _apply_item_change(
        self,
        uow: UnitOfWork,
        change: BatchChangeCreate | BatchChangeUpdate | BatchChangeDeactivate | BatchChangeDelete,
        local_id_map: dict[str, int],
        user_id: UUID,
    ) -> BatchChangeResult:
        """Apply a single item change."""
        try:
            if isinstance(change, BatchChangeCreate):
                payload = change.payload
                if isinstance(payload, BatchChangeItemPayload):
                    # Resolve local references
                    category_id = payload.category_id
                    if payload.category_local_id and payload.category_local_id in local_id_map:
                        category_id = local_id_map[payload.category_local_id]
                    
                    unit_id = payload.unit_id
                    if payload.unit_local_id and payload.unit_local_id in local_id_map:
                        unit_id = local_id_map[payload.unit_local_id]
                    
                    if unit_id is None:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="unit_id or unit_local_id is required for item create"
                        )
                    
                    create_payload = ItemCreateRequest(
                        sku=payload.sku,
                        name=payload.name,
                        category_id=category_id,
                        unit_id=unit_id,
                        description=payload.description,
                        hashtags=payload.hashtags,
                        is_active=payload.is_active,
                        requires_review=payload.requires_review,
                    )
                    item = await self.create_item(uow, create_payload, user_id)
                    return BatchChangeResult(
                        local_id=change.local_id,
                        entity_type="item",
                        action="create",
                        status="applied",
                        entity_id=item.id,
                    )
            elif isinstance(change, BatchChangeUpdate):
                payload = change.payload
                if isinstance(payload, BatchChangeUpdatePayload) and change.entity_id:
                    item = await self.update_item(uow, change.entity_id, payload, updated_by_user_id=user_id)
                    return BatchChangeResult(
                        local_id=change.local_id,
                        entity_type="item",
                        action="update",
                        status="applied",
                        entity_id=item.id,
                    )
            elif isinstance(change, BatchChangeDeactivate):
                if change.entity_id:
                    payload = ItemUpdateRequest(is_active=False)
                    item = await self.update_item(uow, change.entity_id, payload, updated_by_user_id=user_id)
                    return BatchChangeResult(
                        local_id=change.local_id,
                        entity_type="item",
                        action="deactivate",
                        status="applied",
                        entity_id=item.id,
                    )
            elif isinstance(change, BatchChangeDelete):
                if change.entity_id:
                    await self.delete_item(uow, change.entity_id, user_id)
                    return BatchChangeResult(
                        local_id=change.local_id,
                        entity_type="item",
                        action="delete",
                        status="applied",
                        entity_id=change.entity_id,
                    )
        except HTTPException as e:
            return BatchChangeResult(
                local_id=change.local_id,
                entity_type="item",
                action=change.action,
                status="error",
                error_code=e.detail if isinstance(e.detail, str) else "unknown_error",
                error_message=str(e.detail),
            )
        
        return BatchChangeResult(
            local_id=change.local_id,
            entity_type="item",
            action=change.action,
            status="error",
            error_code="invalid_payload",
            error_message="Invalid payload for item change",
        )
