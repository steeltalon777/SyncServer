from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import HTTPException, status

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


class CatalogAdminService:
    async def create_unit(self, uow: UnitOfWork, payload: UnitCreateRequest) -> Unit:
        await self._ensure_unit_unique(uow, name=payload.name, symbol=payload.symbol)

        unit = Unit(
            id=payload.id or uuid4(),
            name=payload.name,
            symbol=payload.symbol,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
        )
        return await uow.catalog.create_unit(unit)

    async def update_unit(self, uow: UnitOfWork, unit_id: UUID, payload: UnitUpdateRequest) -> Unit:
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
            unit.symbol = payload.symbol

        if payload.sort_order is not None:
            unit.sort_order = payload.sort_order
        if payload.is_active is not None:
            unit.is_active = payload.is_active

        return await uow.catalog.update_unit(unit)

    async def create_category(self, uow: UnitOfWork, payload: CategoryCreateRequest) -> Category:
        category_id = payload.id or uuid4()
        if payload.parent_id == category_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="category parent_id cannot equal id")

        if payload.parent_id is not None:
            parent = await uow.catalog.get_category_by_id(payload.parent_id)
            if parent is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="parent category not found")

        sibling = await uow.catalog.get_category_by_parent_and_name(payload.parent_id, payload.name)
        if sibling is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="category name already exists for parent")

        category = Category(
            id=category_id,
            name=payload.name,
            code=payload.code,
            parent_id=payload.parent_id,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
        )
        return await uow.catalog.create_category(category)

    async def update_category(self, uow: UnitOfWork, category_id: UUID, payload: CategoryUpdateRequest) -> Category:
        category = await uow.catalog.get_category_by_id(category_id)
        if category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="category not found")

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
        if "code" in payload.model_fields_set:
            category.code = payload.code
        if "sort_order" in payload.model_fields_set:
            category.sort_order = payload.sort_order
        if payload.is_active is not None:
            category.is_active = payload.is_active

        return await uow.catalog.update_category(category)

    async def create_item(self, uow: UnitOfWork, payload: ItemCreateRequest) -> Item:
        await self._validate_item_relations(uow, payload.category_id, payload.unit_id)
        await self._ensure_item_sku_unique(uow, payload.sku)

        item = Item(
            id=payload.id or uuid4(),
            sku=payload.sku,
            name=payload.name,
            category_id=payload.category_id,
            unit_id=payload.unit_id,
            description=payload.description,
            is_active=payload.is_active,
        )
        return await uow.catalog.create_item(item)

    async def update_item(self, uow: UnitOfWork, item_id: UUID, payload: ItemUpdateRequest) -> Item:
        item = await uow.catalog.get_item_by_id(item_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")

        category_id = payload.category_id if payload.category_id is not None else item.category_id
        unit_id = payload.unit_id if payload.unit_id is not None else item.unit_id
        await self._validate_item_relations(uow, category_id, unit_id)

        if payload.sku is not None and payload.sku != item.sku:
            existing = await uow.catalog.get_item_by_sku(payload.sku)
            if existing is not None and existing.id != item.id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="item sku already exists")
            item.sku = payload.sku

        if payload.name is not None:
            item.name = payload.name
        if payload.category_id is not None:
            item.category_id = payload.category_id
        if payload.unit_id is not None:
            item.unit_id = payload.unit_id
        if "description" in payload.model_fields_set:
            item.description = payload.description
        if payload.is_active is not None:
            item.is_active = payload.is_active

        return await uow.catalog.update_item(item)

    async def _ensure_unit_unique(self, uow: UnitOfWork, name: str, symbol: str) -> None:
        if await uow.catalog.get_unit_by_name(name):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="unit name already exists")
        if await uow.catalog.get_unit_by_symbol(symbol):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="unit symbol already exists")

    async def _validate_no_category_cycle(self, uow: UnitOfWork, category_id: UUID, new_parent_id: UUID) -> None:
        ancestors = await uow.catalog.list_category_ancestors(new_parent_id)
        if category_id in ancestors:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="category cycle detected")

    async def _validate_item_relations(self, uow: UnitOfWork, category_id: UUID, unit_id: UUID) -> None:
        if await uow.catalog.get_category_by_id(category_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="category not found")
        if await uow.catalog.get_unit_by_id(unit_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unit not found")

    async def _ensure_item_sku_unique(self, uow: UnitOfWork, sku: str | None) -> None:
        if sku is None:
            return
        existing = await uow.catalog.get_item_by_sku(sku)
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="item sku already exists")
