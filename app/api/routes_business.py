from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, Request

from app.api.deps import (
    get_request_id,
    get_uow,
    require_service_auth,
    require_acting_user,
)
from app.schemas.catalog import (
    CatalogCategoriesResponse,
    CatalogItemsResponse,
    CatalogRequest,
    CatalogUnitsResponse,
    CategoryTreeNode,
)
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/business")
logger = logging.getLogger(__name__)


@router.post("/catalog/items", response_model=CatalogItemsResponse)
async def business_list_items(
    payload: CatalogRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: str = Header(alias="X-Acting-Site-Id"),
) -> CatalogItemsResponse:
    """List catalog items with service authentication and acting user context."""
    # Validate service authentication
    await require_service_auth(request=request, authorization=authorization)
    
    # Validate acting user context
    user_context = await require_acting_user(
        request=request,
        uow=uow,
        x_acting_user_id=x_acting_user_id,
        x_acting_site_id=x_acting_site_id,
    )
    
    async with uow:
        items = await uow.catalog.list_items(
            updated_after=payload.updated_after,
            limit=payload.limit,
        )
    
    next_updated_after = max((item.updated_at for item in items), default=None)
    logger.info(
        "request_id=%s business_catalog_items user_id=%s site_id=%s returned=%s",
        get_request_id(request),
        user_context["user_id"],
        user_context["site_id"],
        len(items),
    )
    
    return CatalogItemsResponse(
        items=items,
        server_time=datetime.now(UTC),
        next_updated_after=next_updated_after,
    )


@router.post("/catalog/categories", response_model=CatalogCategoriesResponse)
async def business_list_categories(
    payload: CatalogRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: str = Header(alias="X-Acting-Site-Id"),
) -> CatalogCategoriesResponse:
    """List catalog categories with service authentication and acting user context."""
    # Validate service authentication
    await require_service_auth(request=request, authorization=authorization)
    
    # Validate acting user context
    user_context = await require_acting_user(
        request=request,
        uow=uow,
        x_acting_user_id=x_acting_user_id,
        x_acting_site_id=x_acting_site_id,
    )
    
    async with uow:
        categories = await uow.catalog.list_categories(
            updated_after=payload.updated_after,
            limit=payload.limit,
        )
    
    next_updated_after = max((category.updated_at for category in categories), default=None)
    logger.info(
        "request_id=%s business_catalog_categories user_id=%s site_id=%s returned=%s",
        get_request_id(request),
        user_context["user_id"],
        user_context["site_id"],
        len(categories),
    )
    
    return CatalogCategoriesResponse(
        categories=categories,
        server_time=datetime.now(UTC),
        next_updated_after=next_updated_after,
    )


@router.post("/catalog/units", response_model=CatalogUnitsResponse)
async def business_list_units(
    payload: CatalogRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: str = Header(alias="X-Acting-Site-Id"),
) -> CatalogUnitsResponse:
    """List catalog units with service authentication and acting user context."""
    # Validate service authentication
    await require_service_auth(request=request, authorization=authorization)
    
    # Validate acting user context
    user_context = await require_acting_user(
        request=request,
        uow=uow,
        x_acting_user_id=x_acting_user_id,
        x_acting_site_id=x_acting_site_id,
    )
    
    async with uow:
        units = await uow.catalog.list_units(
            updated_after=payload.updated_after,
            limit=payload.limit,
        )
    
    next_updated_after = max((unit.updated_at for unit in units), default=None)
    logger.info(
        "request_id=%s business_catalog_units user_id=%s site_id=%s returned=%s",
        get_request_id(request),
        user_context["user_id"],
        user_context["site_id"],
        len(units),
    )
    
    return CatalogUnitsResponse(
        units=units,
        server_time=datetime.now(UTC),
        next_updated_after=next_updated_after,
    )


@router.get("/catalog/categories/tree", response_model=list[CategoryTreeNode])
async def business_get_categories_tree(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: str = Header(alias="X-Acting-Site-Id"),
) -> list[CategoryTreeNode]:
    """Get categories tree with service authentication and acting user context."""
    # Validate service authentication
    await require_service_auth(request=request, authorization=authorization)
    
    # Validate acting user context
    user_context = await require_acting_user(
        request=request,
        uow=uow,
        x_acting_user_id=x_acting_user_id,
        x_acting_site_id=x_acting_site_id,
    )
    
    async with uow:
        categories_tree = await uow.catalog.get_categories_tree()
    
    logger.info(
        "request_id=%s business_catalog_categories_tree user_id=%s site_id=%s returned=%s",
        get_request_id(request),
        user_context["user_id"],
        user_context["site_id"],
        len(categories_tree),
    )
    
    return [CategoryTreeNode.model_validate(node) for node in categories_tree]