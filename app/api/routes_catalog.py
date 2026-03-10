from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request

from app.api.deps import auth_catalog_headers, get_request_id, get_uow, require_device_auth
from app.services.uow import UnitOfWork
from app.schemas.catalog import (
    CatalogCategoriesResponse,
    CatalogItemsResponse,
    CatalogRequest,
    CategoryTreeNode,
)

router = APIRouter(prefix="/catalog")
logger = logging.getLogger(__name__)


@router.post("/items", response_model=CatalogItemsResponse)
async def list_items(
    payload: CatalogRequest,
    request: Request,
    auth: dict = Depends(auth_catalog_headers),
    uow: UnitOfWork = Depends(get_uow),
) -> CatalogItemsResponse:
    async with uow:
        await require_device_auth(
            request=request,
            uow=uow,
            site_id=auth["site_id"],
            device_id=auth["device_id"],
            device_token=auth["device_token"],
            client_version=auth["client_version"],
        )
        items = await uow.catalog.list_items(updated_after=payload.updated_after, limit=payload.limit)

    next_updated_after = max((item.updated_at for item in items), default=None)
    logger.info(
        "request_id=%s catalog_items site_id=%s device_id=%s returned=%s",
        get_request_id(request),
        auth["site_id"],
        auth["device_id"],
        len(items),
    )
    return CatalogItemsResponse(
        items=items,
        server_time=datetime.now(UTC),
        next_updated_after=next_updated_after,
    )


@router.post("/categories", response_model=CatalogCategoriesResponse)
async def list_categories(
    payload: CatalogRequest,
    request: Request,
    auth: dict = Depends(auth_catalog_headers),
    uow: UnitOfWork = Depends(get_uow),
) -> CatalogCategoriesResponse:
    async with uow:
        await require_device_auth(
            request=request,
            uow=uow,
            site_id=auth["site_id"],
            device_id=auth["device_id"],
            device_token=auth["device_token"],
            client_version=auth["client_version"],
        )
        categories = await uow.catalog.list_categories(updated_after=payload.updated_after, limit=payload.limit)

    next_updated_after = max((category.updated_at for category in categories), default=None)
    logger.info(
        "request_id=%s catalog_categories site_id=%s device_id=%s returned=%s",
        get_request_id(request),
        auth["site_id"],
        auth["device_id"],
        len(categories),
    )
    return CatalogCategoriesResponse(
        categories=categories,
        server_time=datetime.now(UTC),
        next_updated_after=next_updated_after,
    )


@router.get("/categories", response_model=list[CategoryTreeNode])
async def get_categories_tree(
    request: Request,
    auth: dict = Depends(auth_catalog_headers),
    uow: UnitOfWork = Depends(get_uow),
) -> list[CategoryTreeNode]:
    async with uow:
        await require_device_auth(
            request=request,
            uow=uow,
            site_id=auth["site_id"],
            device_id=auth["device_id"],
            device_token=auth["device_token"],
            client_version=auth["client_version"],
        )
        categories_tree = await uow.catalog.get_categories_tree()

    logger.info(
        "request_id=%s catalog_categories_tree site_id=%s device_id=%s returned=%s",
        get_request_id(request),
        auth["site_id"],
        auth["device_id"],
        len(categories_tree),
    )

    return [CategoryTreeNode.model_validate(node) for node in categories_tree]