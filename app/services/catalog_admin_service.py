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
from app.core.search_utils import normalize_for_storage
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
    BatchChangeMerge,
    BatchChangeResult,
    BatchChangeUnitPayload,
    BatchChangeCategoryPayload,
    BatchChangeItemPayload,
    BatchChangeUpdatePayload,
)
from fastapi import HTTPException, status

from app.services.audit_helper import record_audit_event
from app.services.uow import UnitOfWork

logger = structlog.get_logger()


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
        created = await uow.catalog.create_unit(unit)
        await record_audit_event(
            uow,
            event_type="unit.create",
            actor_user_id=created_by_user_id,
            entity_type="unit",
            entity_id=str(created.id),
            summary=f"Создана единица измерения «{created.name}»",
        )
        return created

    async def bulk_create_units(self, uow: UnitOfWork, payload: UnitBulkCreateRequest, created_by_user_id: UUID | None = None) -> list[Unit]:
        seen_names: set[str] = set()
        seen_symbols: set[str] = set()
        for item in payload.items:
            normalized_name = normalize_for_storage(item.name)
            normalized_symbol = normalize_for_storage(item.symbol)
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

        changes: dict[str, dict[str, object]] = {}

        if payload.name is not None and payload.name != unit.name:
            existing = await uow.catalog.get_unit_by_name(payload.name)
            if existing is not None and existing.id != unit.id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="unit name already exists")
            changes["name"] = {"old": unit.name, "new": payload.name}
            unit.name = payload.name

        if payload.symbol is not None and payload.symbol != unit.symbol:
            existing = await uow.catalog.get_unit_by_symbol(payload.symbol)
            if existing is not None and existing.id != unit.id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="unit symbol already exists")
            previous_symbol = unit.symbol
            changes["symbol"] = {"old": unit.symbol, "new": payload.symbol}
            unit.symbol = payload.symbol
            if unit.code is None or unit.code == previous_symbol.upper():
                unit.code = payload.symbol.upper()

        if payload.sort_order is not None:
            changes["sort_order"] = {"old": unit.sort_order, "new": payload.sort_order}
            unit.sort_order = payload.sort_order
        if payload.is_active is not None:
            changes["is_active"] = {"old": unit.is_active, "new": payload.is_active}
            unit.is_active = payload.is_active

        if updated_by_user_id is not None:
            unit.updated_by_user_id = updated_by_user_id
        result = await uow.catalog.update_unit(unit)
        if changes:
            await record_audit_event(
                uow,
                event_type="unit.update",
                actor_user_id=updated_by_user_id,
                entity_type="unit",
                entity_id=str(unit_id),
                summary=f"Изменена единица измерения «{result.name}»",
                changes=changes,
            )
        return result

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
            normalized_name=normalize_for_storage(payload.name),
            code=payload.code,
            parent_id=payload.parent_id,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
        )
        if created_by_user_id is not None:
            category.created_by_user_id = created_by_user_id
        created = await uow.catalog.create_category(category)
        await record_audit_event(
            uow,
            event_type="category.create",
            actor_user_id=created_by_user_id,
            entity_type="category",
            entity_id=str(created.id),
            summary=f"Создана категория «{created.name}»",
        )
        return created

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

        changes: dict[str, dict[str, object]] = {}

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
            changes["parent_id"] = {"old": category.parent_id, "new": payload.parent_id}
            category.parent_id = payload.parent_id

        sibling = await uow.catalog.get_category_by_parent_and_name(target_parent_id, target_name)
        if sibling is not None and sibling.id != category.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="category name already exists for parent")

        if payload.name is not None:
            changes["name"] = {"old": category.name, "new": payload.name}
            category.name = payload.name
            category.normalized_name = normalize_for_storage(payload.name)
        if "code" in payload.model_fields_set:
            changes["code"] = {"old": category.code, "new": payload.code}
            category.code = payload.code
        if "sort_order" in payload.model_fields_set:
            changes["sort_order"] = {"old": category.sort_order, "new": payload.sort_order}
            category.sort_order = payload.sort_order
        if payload.is_active is not None:
            changes["is_active"] = {"old": category.is_active, "new": payload.is_active}
            category.is_active = payload.is_active

        if updated_by_user_id is not None:
            category.updated_by_user_id = updated_by_user_id
        result = await uow.catalog.update_category(category)
        if changes:
            await record_audit_event(
                uow,
                event_type="category.update",
                actor_user_id=updated_by_user_id,
                entity_type="category",
                entity_id=str(category_id),
                summary=f"Изменена категория «{result.name}»",
                changes=changes,
            )
        return result

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
            normalized_name=normalize_for_storage(payload.name),
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
        created = await uow.catalog.create_item(item)
        await record_audit_event(
            uow,
            event_type="item.create",
            actor_user_id=created_by_user_id,
            entity_type="item",
            entity_id=str(created.id),
            summary=f"Создан ТМЦ «{created.name}» (категория: {category.name})",
        )
        return created

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

        changes: dict[str, dict[str, object]] = {}

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
            changes["sku"] = {"old": item.sku, "new": payload.sku}
            item.sku = payload.sku

        if payload.name is not None:
            changes["name"] = {"old": item.name, "new": payload.name}
            item.name = payload.name
            item.normalized_name = normalize_for_storage(payload.name)
        if "category_id" in payload.model_fields_set:
            changes["category_id"] = {"old": item.category_id, "new": category_id}
            item.category_id = category_id
        if payload.unit_id is not None:
            changes["unit_id"] = {"old": item.unit_id, "new": payload.unit_id}
            item.unit_id = payload.unit_id
        if "description" in payload.model_fields_set:
            changes["description"] = {"old": item.description, "new": payload.description}
            item.description = payload.description
        if "hashtags" in payload.model_fields_set:
            changes["hashtags"] = {"old": item.hashtags, "new": payload.hashtags}
            item.hashtags = payload.hashtags
        if payload.is_active is not None:
            changes["is_active"] = {"old": item.is_active, "new": payload.is_active}
            item.is_active = payload.is_active

        if updated_by_user_id is not None:
            item.updated_by_user_id = updated_by_user_id
        result = await uow.catalog.update_item(item)
        if changes:
            await record_audit_event(
                uow,
                event_type="item.update",
                actor_user_id=updated_by_user_id,
                entity_type="item",
                entity_id=str(item_id),
                summary=f"Изменён ТМЦ «{result.name}»",
                changes=changes,
            )
        return result

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
        unit = await uow.catalog.get_unit_by_id(unit_id)
        if unit is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unit not found")
        if not unit.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unit is not active")

    async def _resolve_item_category(self, uow: UnitOfWork, category_id: int | None) -> Category:
        if category_id is not None:
            category = await uow.catalog.get_category_by_id(category_id)
            if category is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="category not found")
            if not category.is_active:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="category is not active")
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
            normalized_name=normalize_for_storage(UNCATEGORIZED_CATEGORY_NAME),
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

        TZ-AUDIT_BACKEND_FOUNDATION §10.3 — Storage Foundation ordering:

        1. Validate.
        2. INSERT parent AuditEvent(item.merge). FLUSH so event_id is
           available for the system ADJUSTMENT sub-events.
        3. Transfer balances via system ADJUSTMENT ops. Each op has
           origin="system", system_reason="item_merge",
           initiated_by_user_id = resolved_by_user_id. submit_operation
           inherits parent_event_id from uow.audit_parent_event_id, so
           the resulting operation.submit events become children of the
           merge event in audit_events.parent_event_id.
        4. Insert audit_item_effects rows (effect_type=merge_write_off /
           merge_receipt) for each balance change. These are produced
           inside submit_operation.
        5. Reassign all OperationLine.item_id rows — the destructive
           mutation is now safe because the effect journal already
           preserves the source-item reference.
        6. Archive inventory subject + deactivate source item.
        7. Insert audit_event_resources: merge_source, merge_target,
           generated → each system ADJUSTMENT operation.
        """
        # ── Validation ───────────────────────────────────────────────
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

        # ── Step 1: parent audit event ────────────────────────────────
        merge_event = await record_audit_event(
            uow,
            event_type="item.merge",
            event_version=2,
            actor_user_id=resolved_by_user_id,
            entity_type="item",
            entity_id=str(target_item_id),
            summary=(
                f"Слияние: ТМЦ {source_item_id} → {target_item_id}"
                + (f" ({comment})" if comment else "")
            ),
            changes={
                "source_item_id": source_item_id,
                "target_item_id": target_item_id,
                "comment": comment,
                "balances_transferred": [],
                "op_lines_reassigned_count": 0,
            },
            outcome="success",
        )

        # Set up UoW context for system ADJUSTMENT submits that follow.
        previous_parent_event_id = getattr(uow, "audit_parent_event_id", None)
        previous_caused_by_event_id = getattr(uow, "audit_caused_by_event_id", None)
        uow.audit_parent_event_id = merge_event.event_id
        uow.audit_caused_by_event_id = int(merge_event.id)

        generated_adjustment_ids: list[UUID] = []
        balances_transferred_summary: list[dict[str, object]] = []

        try:
            # ── Step 2: system ADJUSTMENT balance transfer ────────────
            source_subject = await uow.inventory_subjects.get_by_item_id(source_item_id)
            target_subject = await uow.inventory_subjects.get_or_create_for_item(item_id=target_item_id)

            if source_subject is not None and source_subject.archived_at is None:
                from app.services.operations_service import OperationsService

                source_balances = await uow.balances.get_all_by_inventory_subject(int(source_subject.id))
                for balance_row in source_balances:
                    qty = Decimal(balance_row.qty)
                    if qty == 0:
                        continue

                    site_id = int(balance_row.site_id)
                    note = (
                        f"[catalog merge] item={source_item_id} -> item={target_item_id}: "
                        f"balance transfer site={site_id} qty={qty}"
                    )

                    # Write-off from source — effect_type override per side
                    uow.audit_effect_type_override = "merge_write_off"
                    write_off = await uow.operations.create_operation(
                        site_id=site_id,
                        operation_type="ADJUSTMENT",
                        created_by_user_id=resolved_by_user_id,
                        notes=note,
                        effective_at=datetime.now(UTC),
                        origin="system",
                        system_reason="item_merge",
                        initiated_by_user_id=resolved_by_user_id,
                    )
                    await uow.operations.create_operation_line(
                        operation_id=write_off.id,
                        line_number=1,
                        inventory_subject_id=int(source_subject.id),
                        item_id=source_item_id,
                        qty=-qty,
                        comment=note,
                    )
                    await OperationsService.submit_operation(
                        uow=uow,
                        operation_id=write_off.id,
                        user_id=resolved_by_user_id,
                    )
                    generated_adjustment_ids.append(write_off.id)

                    # Receipt to target
                    uow.audit_effect_type_override = "merge_receipt"
                    receipt_op = await uow.operations.create_operation(
                        site_id=site_id,
                        operation_type="ADJUSTMENT",
                        created_by_user_id=resolved_by_user_id,
                        notes=note,
                        effective_at=datetime.now(UTC),
                        origin="system",
                        system_reason="item_merge",
                        initiated_by_user_id=resolved_by_user_id,
                    )
                    await uow.operations.create_operation_line(
                        operation_id=receipt_op.id,
                        line_number=1,
                        inventory_subject_id=int(target_subject.id),
                        item_id=target_item_id,
                        qty=qty,
                        comment=note,
                    )
                    await OperationsService.submit_operation(
                        uow=uow,
                        operation_id=receipt_op.id,
                        user_id=resolved_by_user_id,
                    )
                    generated_adjustment_ids.append(receipt_op.id)
                    balances_transferred_summary.append({"site_id": site_id, "qty": str(qty)})

            # ── Step 3: reassign OperationLine rows ──────────────────
            from app.models.operation import OperationLine
            from sqlalchemy import update as sa_update

            reassign_result = await uow.session.execute(
                sa_update(OperationLine.__table__)
                .where(OperationLine.__table__.c.item_id == source_item_id)
                .values(item_id=target_item_id)
                .returning(OperationLine.__table__.c.id)
            )
            op_lines_count = len(list(reassign_result)) if reassign_result else 0

            # ── Step 4: archive + deactivate ─────────────────────────
            if source_subject is not None and source_subject.archived_at is None:
                await uow.inventory_subjects.archive(int(source_subject.id))

            now = datetime.now(UTC)
            source.is_active = False
            source.merged_into_id = target_item_id
            source.merged_at = now
            source.merged_by_user_id = resolved_by_user_id
            source.merge_comment = comment

            await uow.catalog.update_item(source)

            # ── Step 5: extend parent changes with the discovered facts
            change_payload = merge_event.changes if isinstance(merge_event.changes, dict) else {}
            change_payload["op_lines_reassigned_count"] = op_lines_count
            change_payload["balances_transferred"] = balances_transferred_summary
            merge_event.changes = change_payload

            # ── Step 6: resource links ───────────────────────────────
            # merge_source points at the source item — its snapshot is taken
            # AFTER deactivate so the snapshot reflects the merged state.
            await uow.audit_events.insert_resource(
                audit_event_id=int(merge_event.id),
                resource_type="item",
                resource_id=str(source_item_id),
                relation="merge_source",
                snapshot_before={"name": source.name, "sku": source.sku, "is_active": True},
                snapshot_after={"is_active": False, "merged_into_id": target_item_id},
            )
            await uow.audit_events.insert_resource(
                audit_event_id=int(merge_event.id),
                resource_type="item",
                resource_id=str(target_item_id),
                relation="merge_target",
                snapshot_before={"name": target.name, "sku": target.sku},
                snapshot_after={"name": target.name, "sku": target.sku},
            )
            for op_id in generated_adjustment_ids:
                await uow.audit_events.insert_resource(
                    audit_event_id=int(merge_event.id),
                    resource_type="operation",
                    resource_id=str(op_id),
                    relation="generated",
                )
        finally:
            # Always restore UoW context so any later calls do not inherit
            # the merge orchestration tags.
            uow.audit_parent_event_id = previous_parent_event_id
            uow.audit_caused_by_event_id = previous_caused_by_event_id
            uow.audit_effect_type_override = None

        logger.info(
            "merge_items",
            source_item_id=source_item_id,
            target_item_id=target_item_id,
            user_id=str(resolved_by_user_id),
            generated_adjustments=len(generated_adjustment_ids),
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

        TZ-AUDIT_BACKEND_FOUNDATION §10.2 — emits a category.merge audit
        event with merge_source/merge_target resource links plus
        category_changed rows for each moved item and reparented rows
        for each moved subcategory.
        """
        from app.models.item import Item as ItemModel
        from app.models.category import Category as CategoryModel
        from sqlalchemy import update as sa_update

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

        # Capture the affected items/subcategories BEFORE they are moved so
        # the resource edges point at the right entities.
        items_moved = await uow.catalog.list_items_by_category(source_category_id)
        subcats_moved = await uow.catalog.list_categories_by_parent(source_category_id)

        # Move all items from source category to target category
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

        # ── Audit event (Phase 1) ────────────────────────────────────
        merge_event = await record_audit_event(
            uow,
            event_type="category.merge",
            event_version=2,
            actor_user_id=resolved_by_user_id,
            entity_type="category",
            entity_id=str(target_category_id),
            summary=(
                f"Слияние категории {source_category_id} → {target_category_id}"
                + (f" ({comment})" if comment else "")
            ),
            changes={
                "source_category_id": source_category_id,
                "target_category_id": target_category_id,
                "comment": comment,
                "items_moved_count": len(items_moved),
                "subcategories_reparented_count": len(subcats_moved),
            },
            outcome="success",
        )
        await uow.audit_events.insert_resource(
            audit_event_id=int(merge_event.id),
            resource_type="category",
            resource_id=str(source_category_id),
            relation="merge_source",
            snapshot_before={"name": source.name, "is_active": True},
            snapshot_after={"is_active": False, "merged_into_id": target_category_id},
        )
        await uow.audit_events.insert_resource(
            audit_event_id=int(merge_event.id),
            resource_type="category",
            resource_id=str(target_category_id),
            relation="merge_target",
        )
        for item in items_moved:
            await uow.audit_events.insert_resource(
                audit_event_id=int(merge_event.id),
                resource_type="item",
                resource_id=str(item.id),
                relation="category_changed",
                snapshot_before={"category_id": source_category_id},
                snapshot_after={"category_id": target_category_id},
            )
        for subcat in subcats_moved:
            await uow.audit_events.insert_resource(
                audit_event_id=int(merge_event.id),
                resource_type="category",
                resource_id=str(subcat.id),
                relation="reparented",
                snapshot_before={"parent_id": source_category_id},
                snapshot_after={"parent_id": target_category_id},
            )

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

        TZ-AUDIT_BACKEND_FOUNDATION §10.6 — at the start of the batch we
        stamp `uow.batch_correlation_id` so every audit event recorded by
        the sub-helpers (create_item, update_item, merge_items, ...)
        inherits the same correlation id. After the last change has been
        applied, we emit one summary event with outcome=success (no
        errors) or outcome=partial (some errors).
        """
        # Validate batch structure
        await self._validate_batch(payload)

        # Build local_id -> entity_id mapping for created entities
        local_id_map: dict[str, int] = {}
        results: list[BatchChangeResult] = []
        summary: dict[str, int] = {"create": 0, "update": 0, "deactivate": 0, "delete": 0, "merge": 0, "error": 0}

        # Stamp correlation_id BEFORE any audit-producing child call so the
        # helper picks it up automatically.
        from uuid import uuid4 as _uuid4
        correlation_id = str(_uuid4())
        previous_correlation = getattr(uow, "batch_correlation_id", None)
        uow.batch_correlation_id = correlation_id

        try:
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

            # Process merges: items first, then categories
            item_merges = [c for c in payload.changes if c.entity_type == "item" and c.action == "merge"]
            category_merges = [c for c in payload.changes if c.entity_type == "category" and c.action == "merge"]

            for change in item_merges + category_merges:
                result = await self._apply_merge_change(uow, change, local_id_map, identity.user_id)
                results.append(result)
                if result.status == "applied":
                    summary["merge"] += 1
                else:
                    summary["error"] += 1
        finally:
            uow.batch_correlation_id = previous_correlation

        # Summary event — outcome depends on whether anything errored.
        batch_outcome = "success" if summary["error"] == 0 else "partial"
        batch_event = await record_audit_event(
            uow,
            event_type="catalog.batch.apply",
            event_version=2,
            actor_user_id=identity.user_id,
            entity_type="batch",
            entity_id=correlation_id,
            summary=(
                f"Пакетное изменение каталога: {len(results)} операций"
                + (" (без ошибок)" if batch_outcome == "success" else f" ({summary['error']} ошибок)")
            ),
            changes={
                "total_changes": len(results),
                "results": [
                    {
                        "local_id": r.local_id,
                        "entity_type": r.entity_type,
                        "action": r.action,
                        "status": r.status,
                        "entity_id": r.entity_id,
                        "error_code": r.error_code,
                        "error_message": r.error_message,
                    }
                    for r in results
                ],
            },
            outcome=batch_outcome,
            correlation_id=correlation_id,
        )
        await uow.audit_events.insert_resource(
            audit_event_id=int(batch_event.id),
            resource_type="batch",
            resource_id=correlation_id,
            relation="primary",
        )

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

    async def _apply_merge_change(
        self,
        uow: UnitOfWork,
        change: BatchChangeMerge,
        local_id_map: dict[str, int],
        user_id: UUID,
    ) -> BatchChangeResult:
        try:
            payload = change.payload
            if change.entity_type == "item":
                await self.merge_items(
                    uow,
                    source_item_id=change.entity_id,
                    target_item_id=payload.target_entity_id,
                    comment=payload.comment,
                    resolved_by_user_id=user_id,
                )
            elif change.entity_type == "category":
                await self.merge_categories(
                    uow,
                    source_category_id=change.entity_id,
                    target_category_id=payload.target_entity_id,
                    comment=payload.comment,
                    resolved_by_user_id=user_id,
                )
            return BatchChangeResult(
                local_id=change.local_id,
                entity_type=change.entity_type,
                action="merge",
                status="applied",
                entity_id=change.entity_id,
            )
        except HTTPException as exc:
            return BatchChangeResult(
                local_id=change.local_id,
                entity_type=change.entity_type,
                action="merge",
                status="error",
                error_code=str(exc.status_code),
                error_message=exc.detail,
            )
