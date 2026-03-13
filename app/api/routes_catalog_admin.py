from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.api.deps import (
    get_request_id,
    get_uow,
    require_acting_user,
    require_service_auth,
)
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


def _require_catalog_admin(user_context: dict) -> None:
    if user_context["role"] != "root":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="catalog admin permission required",
        )


@router.post("/units", response_model=UnitResponse)
async def create_unit(
    payload: UnitCreateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> UnitResponse:
    await require_service_auth(request=request, authorization=authorization)

    service = CatalogAdminService()
    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )
        _require_catalog_admin(user_context)

        unit = await service.create_unit(uow, payload)

    logger.info(
        "request_id=%s create_unit unit_id=%s user_id=%s",
        get_request_id(request),
        unit.id,
        user_context["user_id"],
    )
    return UnitResponse.model_validate(unit)


@router.patch("/units/{unit_id}", response_model=UnitResponse)
async def update_unit(
    unit_id: UUID,
    payload: UnitUpdateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> UnitResponse:
    await require_service_auth(request=request, authorization=authorization)

    service = CatalogAdminService()
    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )
        _require_catalog_admin(user_context)

        unit = await service.update_unit(uow, unit_id, payload)

    logger.info(
        "request_id=%s update_unit unit_id=%s user_id=%s",
        get_request_id(request),
        unit.id,
        user_context["user_id"],
    )
    return UnitResponse.model_validate(unit)


@router.post("/categories", response_model=CategoryResponse)
async def create_category(
    payload: CategoryCreateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> CategoryResponse:
    await require_service_auth(request=request, authorization=authorization)

    service = CatalogAdminService()
    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )
        _require_catalog_admin(user_context)

        category = await service.create_category(uow, payload)

    logger.info(
        "request_id=%s create_category category_id=%s user_id=%s",
        get_request_id(request),
        category.id,
        user_context["user_id"],
    )
    return CategoryResponse.model_validate(category)


@router.patch("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: UUID,
    payload: CategoryUpdateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> CategoryResponse:
    await require_service_auth(request=request, authorization=authorization)

    service = CatalogAdminService()
    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )
        _require_catalog_admin(user_context)

        category = await service.update_category(uow, category_id, payload)

    logger.info(
        "request_id=%s update_category category_id=%s user_id=%s",
        get_request_id(request),
        category.id,
        user_context["user_id"],
    )
    return CategoryResponse.model_validate(category)


@router.post("/items", response_model=ItemResponse)
async def create_item(
    payload: ItemCreateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> ItemResponse:
    await require_service_auth(request=request, authorization=authorization)

    service = CatalogAdminService()
    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )
        _require_catalog_admin(user_context)

        item = await service.create_item(uow, payload)

    logger.info(
        "request_id=%s create_item item_id=%s user_id=%s",
        get_request_id(request),
        item.id,
        user_context["user_id"],
    )
    return ItemResponse.model_validate(item)


@router.patch("/items/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: UUID,
    payload: ItemUpdateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> ItemResponse:
    await require_service_auth(request=request, authorization=authorization)

    service = CatalogAdminService()
    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )
        _require_catalog_admin(user_context)

        item = await service.update_item(uow, item_id, payload)

    logger.info(
        "request_id=%s update_item item_id=%s user_id=%s",
        get_request_id(request),
        item.id,
        user_context["user_id"],
    )
    return ItemResponse.model_validate(item)