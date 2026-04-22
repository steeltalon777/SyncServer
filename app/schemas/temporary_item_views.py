from __future__ import annotations

from app.schemas.temporary_item import TemporaryItemResponse


def build_temporary_item_response(entity) -> TemporaryItemResponse:
    unit = getattr(entity, "unit", None)
    category = getattr(entity, "category", None)
    item = getattr(entity, "item", None)
    return TemporaryItemResponse(
        id=entity.id,
        item_id=entity.item_id,
        name=entity.name,
        normalized_name=entity.normalized_name,
        sku=entity.sku,
        unit_id=entity.unit_id,
        unit_name=None if unit is None else unit.name,
        unit_symbol=None if unit is None else unit.symbol,
        category_id=entity.category_id,
        category_name=None if category is None else category.name,
        description=entity.description,
        hashtags=entity.hashtags,
        status=entity.status,
        resolution_note=entity.resolution_note,
        resolved_item_id=entity.resolved_item_id,
        resolution_type=entity.resolution_type,
        created_by_user_id=entity.created_by_user_id,
        resolved_by_user_id=entity.resolved_by_user_id,
        created_at=entity.created_at,
        resolved_at=entity.resolved_at,
        updated_at=entity.updated_at,
        backing_item_is_active=None if item is None else item.is_active,
    )
