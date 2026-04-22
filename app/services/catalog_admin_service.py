from __future__ import annotations

import inspect
import logging
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status

from app.core.catalog_defaults import (
    UNCATEGORIZED_CATEGORY_CODE,
    UNCATEGORIZED_CATEGORY_NAME,
)
from app.models.category import Category
from app.models.item import Item
from app.models.unit import Unit
from app.schemas.catalog import (
    CategoryCreateRequest,
    CategoryUpdateRequest,
    ItemCreateRequest,
    ItemUpdateRequest,
    UnitCreateRequest,
    UnitUpdateRequest,
)
from app.services.uow import UnitOfWork


logger = logging.getLogger(__name__)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.strip().lower().split())


class CatalogAdminService:
    async def create_unit(self, uow: UnitOfWork, payload: UnitCreateRequest) -> Unit:
        await self._ensure_unit_unique(uow, name=payload.name, symbol=payload.symbol)

        unit = Unit(
            code=payload.symbol.upper(),
            name=payload.name,
            symbol=payload.symbol,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
        )
        return await uow.catalog.create_unit(unit)

    async def update_unit(self, uow: UnitOfWork, unit_id: int, payload: UnitUpdateRequest) -> Unit:
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

        return await uow.catalog.update_unit(unit)

    async def create_category(self, uow: UnitOfWork, payload: CategoryCreateRequest) -> Category:
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
        return await uow.catalog.create_category(category)

    async def update_category(self, uow: UnitOfWork, category_id: int, payload: CategoryUpdateRequest) -> Category:
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

        return await uow.catalog.update_category(category)

    async def create_item(self, uow: UnitOfWork, payload: ItemCreateRequest) -> Item:
        category = await self._resolve_item_category(uow, payload.category_id)
        await self._validate_unit_exists(uow, payload.unit_id)
        await self._ensure_item_sku_unique(uow, payload.sku)

        logger.info(
            "catalog_admin_create_item repo_method=%s repo_signature=%s payload_name=%s payload_sku=%s category_id=%s unit_id=%s hashtags_len=%s is_active=%s",
            getattr(uow.catalog.create_item, "__qualname__", repr(uow.catalog.create_item)),
            inspect.signature(uow.catalog.create_item),
            payload.name,
            payload.sku,
            category.id,
            payload.unit_id,
            len(payload.hashtags or []),
            payload.is_active,
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
        )
        return await uow.catalog.create_item(item)

    async def update_item(self, uow: UnitOfWork, item_id: int, payload: ItemUpdateRequest) -> Item:
        item = await uow.catalog.get_item_by_id(item_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")

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
        if item.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="item already deleted")
        if item.is_active:
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
