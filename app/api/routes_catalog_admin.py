from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.api.deps import get_request_id, get_uow
from app.schemas.catalog import (
    CategoryCreateRequest,
    CategoryListResponse,
    CategoryResponse,
    CategoryUpdateRequest,
    ItemCreateRequest,
    ItemListResponse,
    ItemResponse,
    ItemUpdateRequest,
    UnitCreateRequest,
    UnitListResponse,
    UnitResponse,
    UnitUpdateRequest,
)
from app.services.access_guard import AccessGuard
from app.services.access_service import AccessService
from app.services.catalog_admin_service import CatalogAdminService
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/catalog/admin")
logger = logging.getLogger(__name__)


async def _resolve_current_user_uuid(uow: UnitOfWork, x_user_token: UUID | None) -> UUID:
    if not x_user_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing X-User-Token",
        )

    user = await uow.users.get_by_user_token(x_user_token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid X-User-Token",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user is inactive",
        )
    return user.id


async def _require_catalog_admin(
    uow: UnitOfWork,
    user_id: UUID,
    site_id_int: int | None,
) -> None:
    access_service = AccessService(uow)

    if await access_service.is_root(user_id):
        return

    role = await access_service.get_user_role(user_id)
    if role != "chief_storekeeper":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="catalog admin access denied",
        )

    if site_id_int is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Site-Id is required for chief_storekeeper catalog admin actions",
        )

    await AccessGuard.require_catalog_admin_access(
        access_service=access_service,
        user_id=user_id,
        site_id=site_id_int,
    )


@router.post("/units", response_model=UnitResponse)
async def create_unit(
    payload: UnitCreateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_site_id: int | None = Header(default=None, alias="X-Site-Id"),
) -> UnitResponse:
    service = CatalogAdminService()
    async with uow:
        user_id = await _resolve_current_user_uuid(uow, x_user_token)
        await _require_catalog_admin(uow=uow, user_id=user_id, site_id_int=x_site_id)
        unit = await service.create_unit(uow, payload)

    logger.info("request_id=%s create_unit unit_id=%s user_id=%s", get_request_id(request), unit.id, user_id)
    return UnitResponse.model_validate(unit)


@router.patch("/units/{unit_id}", response_model=UnitResponse)
async def update_unit(
    unit_id: int,
    payload: UnitUpdateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_site_id: int | None = Header(default=None, alias="X-Site-Id"),
) -> UnitResponse:
    service = CatalogAdminService()
    async with uow:
        user_id = await _resolve_current_user_uuid(uow, x_user_token)
        await _require_catalog_admin(uow=uow, user_id=user_id, site_id_int=x_site_id)
        unit = await service.update_unit(uow, unit_id, payload)

    logger.info("request_id=%s update_unit unit_id=%s user_id=%s", get_request_id(request), unit.id, user_id)
    return UnitResponse.model_validate(unit)


@router.post("/categories", response_model=CategoryResponse)
async def create_category(
    payload: CategoryCreateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_site_id: int | None = Header(default=None, alias="X-Site-Id"),
) -> CategoryResponse:
    service = CatalogAdminService()
    async with uow:
        user_id = await _resolve_current_user_uuid(uow, x_user_token)
        await _require_catalog_admin(uow=uow, user_id=user_id, site_id_int=x_site_id)
        category = await service.create_category(uow, payload)

    logger.info(
        "request_id=%s create_category category_id=%s user_id=%s",
        get_request_id(request),
        category.id,
        user_id,
    )
    return CategoryResponse.model_validate(category)


@router.patch("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: int,
    payload: CategoryUpdateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_site_id: int | None = Header(default=None, alias="X-Site-Id"),
) -> CategoryResponse:
    service = CatalogAdminService()
    async with uow:
        user_id = await _resolve_current_user_uuid(uow, x_user_token)
        await _require_catalog_admin(uow=uow, user_id=user_id, site_id_int=x_site_id)
        category = await service.update_category(uow, category_id, payload)

    logger.info(
        "request_id=%s update_category category_id=%s user_id=%s",
        get_request_id(request),
        category.id,
        user_id,
    )
    return CategoryResponse.model_validate(category)


@router.post("/items", response_model=ItemResponse)
async def create_item(
    payload: ItemCreateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_site_id: int | None = Header(default=None, alias="X-Site-Id"),
) -> ItemResponse:
    service = CatalogAdminService()
    async with uow:
        user_id = await _resolve_current_user_uuid(uow, x_user_token)
        await _require_catalog_admin(uow=uow, user_id=user_id, site_id_int=x_site_id)
        item = await service.create_item(uow, payload)

    logger.info("request_id=%s create_item item_id=%s user_id=%s", get_request_id(request), item.id, user_id)
    return ItemResponse.model_validate(item)


@router.patch("/items/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: int,
    payload: ItemUpdateRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_site_id: int | None = Header(default=None, alias="X-Site-Id"),
) -> ItemResponse:
    service = CatalogAdminService()
    async with uow:
        user_id = await _resolve_current_user_uuid(uow, x_user_token)
        await _require_catalog_admin(uow=uow, user_id=user_id, site_id_int=x_site_id)
        item = await service.update_item(uow, item_id, payload)

    logger.info("request_id=%s update_item item_id=%s user_id=%s", get_request_id(request), item.id, user_id)
    return ItemResponse.model_validate(item)


@router.get("/units/{unit_id}", response_model=UnitResponse)
async def get_unit(
    unit_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_site_id: int | None = Header(default=None, alias="X-Site-Id"),
) -> UnitResponse:
    service = CatalogAdminService()
    async with uow:
        user_id = await _resolve_current_user_uuid(uow, x_user_token)
        await _require_catalog_admin(uow=uow, user_id=user_id, site_id_int=x_site_id)
        unit = await service.get_unit(uow, unit_id)

    logger.info("request_id=%s get_unit unit_id=%s user_id=%s", get_request_id(request), unit.id, user_id)
    return UnitResponse.model_validate(unit)


@router.delete("/units/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_unit(
    unit_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_site_id: int | None = Header(default=None, alias="X-Site-Id"),
) -> None:
    service = CatalogAdminService()
    async with uow:
        user_id = await _resolve_current_user_uuid(uow, x_user_token)
        await _require_catalog_admin(uow=uow, user_id=user_id, site_id_int=x_site_id)
        await service.delete_unit(uow, unit_id, user_id)

    logger.info("request_id=%s delete_unit unit_id=%s user_id=%s", get_request_id(request), unit_id, user_id)


@router.get("/units", response_model=UnitListResponse)
async def list_units(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_site_id: int | None = Header(default=None, alias="X-Site-Id"),
    include_inactive: bool = False,
    include_deleted: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> UnitListResponse:
    service = CatalogAdminService()
    async with uow:
        user_id = await _resolve_current_user_uuid(uow, x_user_token)
        await _require_catalog_admin(uow=uow, user_id=user_id, site_id_int=x_site_id)
        units, total_count = await service.list_units(
            uow,
            include_inactive=include_inactive,
            include_deleted=include_deleted,
            page=page,
            page_size=page_size,
        )

    logger.info(
        "request_id=%s list_units count=%s page=%s user_id=%s",
        get_request_id(request),
        len(units),
        page,
        user_id,
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
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_site_id: int | None = Header(default=None, alias="X-Site-Id"),
) -> CategoryResponse:
    service = CatalogAdminService()
    async with uow:
        user_id = await _resolve_current_user_uuid(uow, x_user_token)
        await _require_catalog_admin(uow=uow, user_id=user_id, site_id_int=x_site_id)
        category = await service.get_category(uow, category_id)

    logger.info("request_id=%s get_category category_id=%s user_id=%s", get_request_id(request), category.id, user_id)
    return CategoryResponse.model_validate(category)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_site_id: int | None = Header(default=None, alias="X-Site-Id"),
) -> None:
    service = CatalogAdminService()
    async with uow:
        user_id = await _resolve_current_user_uuid(uow, x_user_token)
        await _require_catalog_admin(uow=uow, user_id=user_id, site_id_int=x_site_id)
        await service.delete_category(uow, category_id, user_id)

    logger.info("request_id=%s delete_category category_id=%s user_id=%s", get_request_id(request), category_id, user_id)


@router.get("/categories", response_model=CategoryListResponse)
async def list_categories(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_site_id: int | None = Header(default=None, alias="X-Site-Id"),
    include_inactive: bool = False,
    include_deleted: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> CategoryListResponse:
    service = CatalogAdminService()
    async with uow:
        user_id = await _resolve_current_user_uuid(uow, x_user_token)
        await _require_catalog_admin(uow=uow, user_id=user_id, site_id_int=x_site_id)
        categories, total_count = await service.list_categories(
            uow,
            include_inactive=include_inactive,
            include_deleted=include_deleted,
            page=page,
            page_size=page_size,
        )

    logger.info(
        "request_id=%s list_categories count=%s page=%s user_id=%s",
        get_request_id(request),
        len(categories),
        page,
        user_id,
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
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_site_id: int | None = Header(default=None, alias="X-Site-Id"),
) -> ItemResponse:
    service = CatalogAdminService()
    async with uow:
        user_id = await _resolve_current_user_uuid(uow, x_user_token)
        await _require_catalog_admin(uow=uow, user_id=user_id, site_id_int=x_site_id)
        item = await service.get_item(uow, item_id)

    logger.info("request_id=%s get_item item_id=%s user_id=%s", get_request_id(request), item.id, user_id)
    return ItemResponse.model_validate(item)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_site_id: int | None = Header(default=None, alias="X-Site-Id"),
) -> None:
    service = CatalogAdminService()
    async with uow:
        user_id = await _resolve_current_user_uuid(uow, x_user_token)
        await _require_catalog_admin(uow=uow, user_id=user_id, site_id_int=x_site_id)
        await service.delete_item(uow, item_id, user_id)

    logger.info("request_id=%s delete_item item_id=%s user_id=%s", get_request_id(request), item_id, user_id)


@router.get("/items", response_model=ItemListResponse)
async def list_items(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_site_id: int | None = Header(default=None, alias="X-Site-Id"),
    include_inactive: bool = False,
    include_deleted: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> ItemListResponse:
    service = CatalogAdminService()
    async with uow:
        user_id = await _resolve_current_user_uuid(uow, x_user_token)
        await _require_catalog_admin(uow=uow, user_id=user_id, site_id_int=x_site_id)
        items, total_count = await service.list_items(
            uow,
            include_inactive=include_inactive,
            include_deleted=include_deleted,
            page=page,
            page_size=page_size,
        )

    logger.info(
        "request_id=%s list_items count=%s page=%s user_id=%s",
        get_request_id(request),
        len(items),
        page,
        user_id,
    )
    return ItemListResponse(
        items=[ItemResponse.model_validate(item) for item in items],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )
