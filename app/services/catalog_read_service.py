from __future__ import annotations

import structlog
from datetime import datetime

from app.models.item import Item
from app.models.category import Category
from app.models.unit import Unit
from app.schemas.catalog import (
    ItemsResolveRequest,
    ItemsResolveResponse,
    ResolvedItemDto,
)
from app.services.uow import UnitOfWork

logger = structlog.get_logger()

MAX_MERGE_DEPTH = 16


def _item_status(item: Item) -> str:
    if item.deleted_at is not None:
        return "deleted"
    if not item.is_active:
        if item.merged_into_id is not None:
            return "merged"
        return "inactive"
    return "active"


def _category_unit_usable(cat: Category | None, unit: Unit | None) -> bool:
    if cat is None or cat.deleted_at is not None or not cat.is_active:
        return False
    if unit is None or unit.deleted_at is not None or not unit.is_active:
        return False
    return True


class CatalogReadService:
    @staticmethod
    async def resolve_items(
        uow: UnitOfWork,
        request: ItemsResolveRequest,
    ) -> ItemsResolveResponse:
        raw_items = await uow.catalog.resolve_items_raw(request.item_ids)
        raw_by_id = {item.id: item for item in raw_items}

        resolve_order = list(dict.fromkeys(request.item_ids))
        resolved: list[ResolvedItemDto] = []

        for requested_id in resolve_order:
            item = raw_by_id.get(requested_id)
            if item is None:
                resolved.append(
                    ResolvedItemDto(
                        requested_id=requested_id,
                        status="missing",
                        canonical_item_id=None,
                        canonical_status=None,
                        reason=None,
                        item=None,
                    )
                )
                continue

            status = _item_status(item)

            if status == "active":
                cat = item.category
                unit = item.unit
                if not _category_unit_usable(cat, unit):
                    resolved.append(
                        ResolvedItemDto(
                            requested_id=requested_id,
                            status=status,
                            canonical_item_id=None,
                            canonical_status=None,
                            reason="unusable_category_or_unit",
                            item=None,
                        )
                    )
                    continue

                resolved.append(
                    ResolvedItemDto(
                        requested_id=requested_id,
                        status="active",
                        canonical_item_id=item.id,
                        canonical_status="active",
                        reason=None,
                        item=_item_as_dict(item),
                    )
                )
                continue

            if status == "merged":
                canonical, reason = await CatalogReadService._follow_merge_chain(
                    uow, item, depth=0, seen_ids=None
                )
                if canonical is not None and _item_status(canonical) == "active":
                    cat = canonical.category
                    unit = canonical.unit
                    if _category_unit_usable(cat, unit):
                        resolved.append(
                            ResolvedItemDto(
                                requested_id=requested_id,
                                status="merged",
                                canonical_item_id=canonical.id,
                                canonical_status="active",
                                reason=None,
                                item=_item_as_dict(canonical),
                            )
                        )
                    else:
                        resolved.append(
                            ResolvedItemDto(
                                requested_id=requested_id,
                                status="merged",
                                canonical_item_id=None,
                                canonical_status=None,
                                reason=reason or "target_unusable_category_or_unit",
                                item=None,
                            )
                        )
                else:
                    resolved.append(
                        ResolvedItemDto(
                            requested_id=requested_id,
                            status="merged",
                            canonical_item_id=None,
                            canonical_status=None,
                            reason=reason or "target_unusable",
                            item=None,
                        )
                    )
                continue

            resolved.append(
                ResolvedItemDto(
                    requested_id=requested_id,
                    status=status,
                    canonical_item_id=None,
                    canonical_status=None,
                    reason=None,
                    item=None,
                )
            )

        return ItemsResolveResponse(items=resolved)

    @staticmethod
    async def _follow_merge_chain(
        uow: UnitOfWork,
        item: Item,
        depth: int = 0,
        seen_ids: set[int] | None = None,
    ) -> tuple[Item | None, str | None]:
        if seen_ids is None:
            seen_ids = set()
        if depth > MAX_MERGE_DEPTH:
            return None, "merge_depth_exceeded"

        target_id = item.merged_into_id
        if target_id is None:
            return item, None

        if target_id in seen_ids:
            return None, "merge_cycle"

        seen_ids.add(item.id)
        all_items = await uow.catalog.resolve_items_raw([target_id])
        if not all_items:
            return None, "target_missing"

        target = all_items[0]
        target_status = _item_status(target)

        if target_status == "active":
            seen_ids.add(target.id)
            return await CatalogReadService._follow_merge_chain(
                uow, target, depth + 1, seen_ids
            )

        reason_map = {
            "deleted": "target_deleted",
            "inactive": "target_inactive",
            "merged": "target_merged",
        }
        return None, reason_map.get(target_status, "target_unusable")


def _item_as_dict(item: Item) -> dict:
    cat = item.category
    unit = item.unit
    return {
        "id": item.id,
        "name": item.name,
        "sku": item.sku,
        "category_id": item.category_id,
        "category_name": cat.name if cat else None,
        "unit_id": item.unit_id,
        "unit_symbol": unit.symbol if unit else None,
        "is_active": item.is_active,
    }
