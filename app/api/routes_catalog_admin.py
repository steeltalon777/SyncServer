from __future__ import annotations

import structlog
from uuid import UUID

from app.api.deps import get_request_id, get_uow, require_user_identity
from app.core.identity import Identity
from app.schemas.catalog import (
    CategoryBulkCreateRequest,
    CategoryBulkCreateResponse,
    CategoryCreateRequest,
    CategoryListResponse,
    CategoryMergeRequest,
    CategoryResponse,
    CategoryUpdateRequest,
    ItemCreateRequest,
    ItemListResponse,
    ItemMergeRequest,
    ItemResponse,
    ItemUpdateRequest,
    UnitBulkCreateRequest,
    UnitBulkCreateResponse,
    UnitCreateRequest,
    UnitListResponse,
    UnitResponse,
    UnitUpdateRequest,
    CatalogBatchRequest,
    CatalogBatchResponse,
    BatchChangeResult,
)
from app.services.catalog_admin_service import CatalogAdminService
from app.services.catalog_agent_policy import validate_agent_patch
from app.services.uow import UnitOfWork
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

router = APIRouter(prefix="/catalog/admin")
logger = structlog.get_logger()


async def _require_catalog_admin(identity: Identity) -> None:
    """TZ §5.1: root/chief-only guard for lifecycle actions (delete/deactivate/batch/bulk)."""
    if identity.is_root:
        return

    if identity.role != "chief_storekeeper":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="catalog admin access denied",
        )


async def _require_catalog_admin_or_agent(identity: Identity) -> None:
    """TZ §5.3/§5.4: agent may create item/category/unit and merge via the
    existing contracts. Lifecycle authority stays root/chief-only."""
    if identity.is_agent:
        return
    await _require_catalog_admin(identity)


async def _require_catalog_admin_read(identity: Identity) -> None:
    """TZ §5.5: GET list/detail under /catalog/admin/* is opened to agent
    (read-only surface for inactive/deleted entities)."""
    if identity.is_agent:
        return
    await _require_catalog_admin(identity)


async def _require_catalog_patch(identity: Identity, payload: BaseModel, entity_kind: str) -> None:
    """TZ §5.2: agent PATCH only through the centralized allow-list; known fields
    outside the allow-list are rejected with 403 before the mutation service runs."""
    if identity.is_agent:
        validate_agent_patch(entity_kind, payload.model_dump(exclude_unset=True))
        return
    await _require_catalog_admin(identity)


@router.post("/units", response_model=UnitResponse)
async def create_unit(
    payload: UnitCreateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> UnitResponse:
    service = CatalogAdminService()
    # TZ §5.1: 403 raised before any mutation runs — outside the uow transaction.
    await _require_catalog_admin_or_agent(identity=identity)
    async with uow:
        unit = await service.create_unit(uow, payload, created_by_user_id=identity.user_id)

    logger.info("create_unit", request_id=get_request_id(request), unit_id=unit.id, user_id=identity.user_id)
    return UnitResponse.model_validate(unit)


@router.post("/units/bulk", response_model=UnitBulkCreateResponse)
async def bulk_create_units(
    payload: UnitBulkCreateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> UnitBulkCreateResponse:
    service = CatalogAdminService()
    # TZ §5.5: bulk create stays root/chief-only — 403 raised before the transaction.
    await _require_catalog_admin(identity=identity)
    async with uow:
        units = await service.bulk_create_units(uow, payload, created_by_user_id=identity.user_id)

    logger.info("bulk_create_units", request_id=get_request_id(request), count=len(units), user_id=identity.user_id)
    return UnitBulkCreateResponse(items=[UnitResponse.model_validate(unit) for unit in units])


@router.patch("/units/{unit_id}", response_model=UnitResponse)
async def update_unit(
    unit_id: int,
    payload: UnitUpdateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> UnitResponse:
    service = CatalogAdminService()
    # TZ §5.1: 403 must be raised before the mutation service runs — outside the uow
    # transaction so a rejected agent request cannot roll back unrelated writes.
    await _require_catalog_patch(identity=identity, payload=payload, entity_kind="unit")
    async with uow:
        unit = await service.update_unit(uow, unit_id, payload, updated_by_user_id=identity.user_id)

    logger.info("update_unit", request_id=get_request_id(request), unit_id=unit.id, user_id=identity.user_id)
    return UnitResponse.model_validate(unit)


@router.post("/categories", response_model=CategoryResponse)
async def create_category(
    payload: CategoryCreateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> CategoryResponse:
    service = CatalogAdminService()
    # TZ §5.1: 403 raised before any mutation runs — outside the uow transaction.
    await _require_catalog_admin_or_agent(identity=identity)
    async with uow:
        category = await service.create_category(uow, payload, created_by_user_id=identity.user_id)

    logger.info(
        "create_category",
        request_id=get_request_id(request),
        category_id=category.id,
        user_id=identity.user_id,
    )
    return CategoryResponse.model_validate(category)


@router.post("/categories/bulk", response_model=CategoryBulkCreateResponse)
async def bulk_create_categories(
    payload: CategoryBulkCreateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> CategoryBulkCreateResponse:
    service = CatalogAdminService()
    # TZ §5.5: bulk create stays root/chief-only — 403 raised before the transaction.
    await _require_catalog_admin(identity=identity)
    async with uow:
        categories = await service.bulk_create_categories(uow, payload, created_by_user_id=identity.user_id)

    logger.info(
        "bulk_create_categories",
        request_id=get_request_id(request),
        count=len(categories),
        user_id=identity.user_id,
    )
    return CategoryBulkCreateResponse(items=[CategoryResponse.model_validate(category) for category in categories])


@router.patch("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: int,
    payload: CategoryUpdateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> CategoryResponse:
    service = CatalogAdminService()
    # TZ §5.1: 403 raised before the mutation service — outside the uow transaction.
    await _require_catalog_patch(identity=identity, payload=payload, entity_kind="category")
    async with uow:
        category = await service.update_category(uow, category_id, payload, updated_by_user_id=identity.user_id)

    logger.info(
        "update_category",
        request_id=get_request_id(request),
        category_id=category.id,
        user_id=identity.user_id,
    )
    return CategoryResponse.model_validate(category)


@router.post("/items", response_model=ItemResponse)
async def create_item(
    payload: ItemCreateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> ItemResponse:
    service = CatalogAdminService()
    # TZ §5.1: 403 raised before any mutation runs — outside the uow transaction.
    await _require_catalog_admin_or_agent(identity=identity)
    async with uow:
        item = await service.create_item(uow, payload, created_by_user_id=identity.user_id)

    logger.info("create_item", request_id=get_request_id(request), item_id=item.id, user_id=identity.user_id)
    return ItemResponse.model_validate(item)


@router.patch("/items/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: int,
    payload: ItemUpdateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> ItemResponse:
    service = CatalogAdminService()
    # TZ §5.1: 403 raised before the mutation service — outside the uow transaction.
    await _require_catalog_patch(identity=identity, payload=payload, entity_kind="item")
    async with uow:
        item = await service.update_item(uow, item_id, payload, updated_by_user_id=identity.user_id)

    logger.info("update_item", request_id=get_request_id(request), item_id=item.id, user_id=identity.user_id)
    return ItemResponse.model_validate(item)


@router.get("/units/{unit_id}", response_model=UnitResponse)
async def get_unit(
    unit_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> UnitResponse:
    service = CatalogAdminService()
    # TZ §5.5: GET list/detail is opened to agent (read-only) — guard before transaction.
    await _require_catalog_admin_read(identity=identity)
    async with uow:
        unit = await service.get_unit(uow, unit_id)

    logger.info("get_unit", request_id=get_request_id(request), unit_id=unit.id, user_id=identity.user_id)
    return UnitResponse.model_validate(unit)


@router.delete("/units/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_unit(
    unit_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> None:
    service = CatalogAdminService()
    # TZ §5.5: delete stays root/chief-only — agent gets 403 before the transaction.
    await _require_catalog_admin(identity=identity)
    async with uow:
        await service.delete_unit(uow, unit_id, identity.user_id)

    logger.info("delete_unit", request_id=get_request_id(request), unit_id=unit_id, user_id=identity.user_id)


@router.get("/units", response_model=UnitListResponse)
async def list_units(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    include_inactive: bool = False,
    include_deleted: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> UnitListResponse:
    service = CatalogAdminService()
    # TZ §5.5: GET list/detail is opened to agent (read-only) — guard before transaction.
    await _require_catalog_admin_read(identity=identity)
    async with uow:
        units, total_count = await service.list_units(
            uow,
            include_inactive=include_inactive,
            include_deleted=include_deleted,
            page=page,
            page_size=page_size,
        )

    logger.info(
        "list_units",
        request_id=get_request_id(request),
        count=len(units),
        page=page,
        user_id=identity.user_id,
    )
    return UnitListResponse(
        items=[UnitResponse.model_validate(unit) for unit in units],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/categories/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> CategoryResponse:
    service = CatalogAdminService()
    # TZ §5.5: GET list/detail is opened to agent (read-only) — guard before transaction.
    await _require_catalog_admin_read(identity=identity)
    async with uow:
        category = await service.get_category(uow, category_id)

    logger.info("get_category", request_id=get_request_id(request), category_id=category.id, user_id=identity.user_id)
    return CategoryResponse.model_validate(category)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> None:
    service = CatalogAdminService()
    # TZ §5.5: delete stays root/chief-only — agent gets 403 before the transaction.
    await _require_catalog_admin(identity=identity)
    async with uow:
        await service.delete_category(uow, category_id, identity.user_id)

    logger.info("delete_category", request_id=get_request_id(request), category_id=category_id, user_id=identity.user_id)


@router.get("/categories", response_model=CategoryListResponse)
async def list_categories(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    include_inactive: bool = False,
    include_deleted: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> CategoryListResponse:
    service = CatalogAdminService()
    # TZ §5.5: GET list/detail is opened to agent (read-only) — guard before transaction.
    await _require_catalog_admin_read(identity=identity)
    async with uow:
        categories, total_count = await service.list_categories(
            uow,
            include_inactive=include_inactive,
            include_deleted=include_deleted,
            page=page,
            page_size=page_size,
        )

    logger.info(
        "list_categories",
        request_id=get_request_id(request),
        count=len(categories),
        page=page,
        user_id=identity.user_id,
    )
    return CategoryListResponse(
        items=[CategoryResponse.model_validate(category) for category in categories],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/items/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> ItemResponse:
    service = CatalogAdminService()
    # TZ §5.5: GET list/detail is opened to agent (read-only) — guard before transaction.
    await _require_catalog_admin_read(identity=identity)
    async with uow:
        item = await service.get_item(uow, item_id)

    logger.info("get_item", request_id=get_request_id(request), item_id=item.id, user_id=identity.user_id)
    return ItemResponse.model_validate(item)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> None:
    service = CatalogAdminService()
    # TZ §5.5: delete stays root/chief-only — agent gets 403 before the transaction.
    await _require_catalog_admin(identity=identity)
    async with uow:
        await service.delete_item(uow, item_id, identity.user_id)

    logger.info("delete_item", request_id=get_request_id(request), item_id=item_id, user_id=identity.user_id)


@router.get("/items", response_model=ItemListResponse)
async def list_items(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    include_inactive: bool = False,
    include_deleted: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> ItemListResponse:
    service = CatalogAdminService()
    # TZ §5.5: GET list/detail is opened to agent (read-only) — guard before transaction.
    await _require_catalog_admin_read(identity=identity)
    async with uow:
        items, total_count = await service.list_items(
            uow,
            include_inactive=include_inactive,
            include_deleted=include_deleted,
            page=page,
            page_size=page_size,
        )

    logger.info(
        "list_items",
        request_id=get_request_id(request),
        count=len(items),
        page=page,
        user_id=identity.user_id,
    )
    return ItemListResponse(
        items=[ItemResponse.model_validate(item) for item in items],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.post("/items/merge", response_model=ItemResponse)
async def merge_items(
    payload: ItemMergeRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> ItemResponse:
    await _require_catalog_admin_or_agent(identity=identity)
    service = CatalogAdminService()
    async with uow:
        target = await service.merge_items(
            uow,
            source_item_id=payload.source_item_id,
            target_item_id=payload.target_item_id,
            comment=payload.comment,
            resolved_by_user_id=identity.user_id,
        )
    logger.info("merge_items", request_id=get_request_id(request),
                source_item_id=payload.source_item_id,
                target_item_id=payload.target_item_id,
                user_id=identity.user_id)
    return ItemResponse.model_validate(target)


@router.post("/categories/merge", response_model=CategoryResponse)
async def merge_categories(
    payload: CategoryMergeRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> CategoryResponse:
    await _require_catalog_admin_or_agent(identity=identity)
    service = CatalogAdminService()
    async with uow:
        target = await service.merge_categories(
            uow,
            source_category_id=payload.source_category_id,
            target_category_id=payload.target_category_id,
            comment=payload.comment,
            resolved_by_user_id=identity.user_id,
        )
    logger.info("merge_categories", request_id=get_request_id(request),
                source_category_id=payload.source_category_id,
                target_category_id=payload.target_category_id,
                user_id=identity.user_id)
    return CategoryResponse.model_validate(target)


@router.post("/batch", response_model=CatalogBatchResponse)
async def apply_catalog_batch(
    payload: CatalogBatchRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> CatalogBatchResponse:
    """
    Apply a mixed batch of catalog changes atomically.
    
    All changes in the batch are applied within a single transaction.
    Any failure rolls back the entire batch.
    
    Supported entity types: unit, category, item
    Supported actions: create, update, deactivate, delete
    """
    service = CatalogAdminService()

    # TZ §5.5: /catalog/admin/batch intentionally stays root/chief-only — agent gets
    # 403 before the transaction (batch mixes create/update/deactivate/delete/merge).
    await _require_catalog_admin(identity=identity)
    async with uow:
        results, summary = await service.apply_batch(uow=uow, payload=payload, identity=identity)
    
    # Determine overall status
    overall_status = "applied" if summary["error"] == 0 else "failed"
    
    logger.info(
        "apply_catalog_batch",
        request_id=get_request_id(request),
        status=overall_status,
        summary=summary,
        user_id=identity.user_id,
    )
    
    return CatalogBatchResponse(
        client_batch_id=payload.client_batch_id,
        mode=payload.mode,
        status=overall_status,
        summary=summary,
        records=results,
    )
