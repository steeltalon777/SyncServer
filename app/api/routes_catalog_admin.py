from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api.deps import auth_catalog_headers, get_request_id, get_uow, require_device_auth
from app.schemas.catalog import (
    CategoryCreateRequest,
    CategoryResponse,
    CategoryUpdateRequest,
    ItemCreateRequest,
    ItemResponse,
    ItemUpdateRequest,
    UnitCreateRequest,
    UnitResponse,
    UnitUpdateRequest,
)
from app.services.catalog_admin_service import CatalogAdminService
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/catalog/admin")
logger = logging.getLogger(__name__)


@router.post("/units", response_model=UnitResponse)
async def create_unit(
    payload: UnitCreateRequest,
    request: Request,
    auth: dict = Depends(auth_catalog_headers),
    uow: UnitOfWork = Depends(get_uow),
) -> UnitResponse:
    service = CatalogAdminService()
    async with uow:
        await require_device_auth(
            request=request,
            uow=uow,
            site_id=auth["site_id"],
            device_id=auth["device_id"],
            device_token=auth["device_token"],
            client_version=auth["client_version"],
        )
        unit = await service.create_unit(uow, payload)

    logger.info("request_id=%s create_unit unit_id=%s", get_request_id(request), unit.id)
    return UnitResponse.model_validate(unit)


@router.patch("/units/{unit_id}", response_model=UnitResponse)
async def update_unit(
    unit_id: UUID,
    payload: UnitUpdateRequest,
    request: Request,
    auth: dict = Depends(auth_catalog_headers),
    uow: UnitOfWork = Depends(get_uow),
) -> UnitResponse:
    service = CatalogAdminService()
    async with uow:
        await require_device_auth(
            request=request,
            uow=uow,
            site_id=auth["site_id"],
            device_id=auth["device_id"],
            device_token=auth["device_token"],
            client_version=auth["client_version"],
        )
        unit = await service.update_unit(uow, unit_id, payload)

    logger.info("request_id=%s update_unit unit_id=%s", get_request_id(request), unit.id)
    return UnitResponse.model_validate(unit)


@router.post("/categories", response_model=CategoryResponse)
async def create_category(
    payload: CategoryCreateRequest,
    request: Request,
    auth: dict = Depends(auth_catalog_headers),
    uow: UnitOfWork = Depends(get_uow),
) -> CategoryResponse:
    service = CatalogAdminService()
    async with uow:
        await require_device_auth(
            request=request,
            uow=uow,
            site_id=auth["site_id"],
            device_id=auth["device_id"],
            device_token=auth["device_token"],
            client_version=auth["client_version"],
        )
        category = await service.create_category(uow, payload)

    logger.info("request_id=%s create_category category_id=%s", get_request_id(request), category.id)
    return CategoryResponse.model_validate(category)


@router.patch("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: UUID,
    payload: CategoryUpdateRequest,
    request: Request,
    auth: dict = Depends(auth_catalog_headers),
    uow: UnitOfWork = Depends(get_uow),
) -> CategoryResponse:
    service = CatalogAdminService()
    async with uow:
        await require_device_auth(
            request=request,
            uow=uow,
            site_id=auth["site_id"],
            device_id=auth["device_id"],
            device_token=auth["device_token"],
            client_version=auth["client_version"],
        )
        category = await service.update_category(uow, category_id, payload)

    logger.info("request_id=%s update_category category_id=%s", get_request_id(request), category.id)
    return CategoryResponse.model_validate(category)


@router.post("/items", response_model=ItemResponse)
async def create_item(
    payload: ItemCreateRequest,
    request: Request,
    auth: dict = Depends(auth_catalog_headers),
    uow: UnitOfWork = Depends(get_uow),
) -> ItemResponse:
    service = CatalogAdminService()
    async with uow:
        await require_device_auth(
            request=request,
            uow=uow,
            site_id=auth["site_id"],
            device_id=auth["device_id"],
            device_token=auth["device_token"],
            client_version=auth["client_version"],
        )
        item = await service.create_item(uow, payload)

    logger.info("request_id=%s create_item item_id=%s", get_request_id(request), item.id)
    return ItemResponse.model_validate(item)


@router.patch("/items/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: UUID,
    payload: ItemUpdateRequest,
    request: Request,
    auth: dict = Depends(auth_catalog_headers),
    uow: UnitOfWork = Depends(get_uow),
) -> ItemResponse:
    service = CatalogAdminService()
    async with uow:
        await require_device_auth(
            request=request,
            uow=uow,
            site_id=auth["site_id"],
            device_id=auth["device_id"],
            device_token=auth["device_token"],
            client_version=auth["client_version"],
        )
        item = await service.update_item(uow, item_id, payload)

    logger.info("request_id=%s update_item item_id=%s", get_request_id(request), item.id)
    return ItemResponse.model_validate(item)
