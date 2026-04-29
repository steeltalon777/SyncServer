from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import (
    get_request_id,
    get_uow,
    require_user_identity,
)
from app.core.identity import Identity
from app.schemas.admin import SiteFilter
from app.schemas.catalog import (
    CatalogBrowseCategoriesResponse,
    CatalogBrowseItemsResponse,
    CatalogCategoriesResponse,
    CatalogItemsResponse,
    CatalogSitesResponse,
    CatalogUnitsResponse,
    CategoryParentChainResponse,
    CategoryTreeNode,
)
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/catalog")
logger = logging.getLogger(__name__)

DEFAULT_CATEGORY_READ_INCLUDES = {
    "parent",
    "parent_chain_summary",
    "items_preview",
}
SUPPORTED_CATEGORY_READ_INCLUDES = set(DEFAULT_CATEGORY_READ_INCLUDES)


async def _resolve_accessible_site_ids(uow: UnitOfWork, identity: Identity) -> list[int]:
    if identity.user is None:
        return []

    sites, _ = await uow.sites.list_sites(
        filter=SiteFilter(is_active=True),
        user_site_ids=None,
        page=1,
        page_size=1000,
    )
    return [site.id for site in sites]


def _require_catalog_read_access(identity: Identity, accessible_site_ids: list[int], site_id: int | None = None) -> None:
    if identity.user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="catalog read access denied")
    if site_id is not None and site_id not in accessible_site_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="requested site not found",
        )


def _parse_category_read_includes(include: str | None) -> set[str]:
    if include is None or not include.strip():
        return set(DEFAULT_CATEGORY_READ_INCLUDES)

    values = {
        raw_value.strip()
        for raw_value in include.split(",")
        if raw_value.strip()
    }
    invalid_values = values - SUPPORTED_CATEGORY_READ_INCLUDES
    if invalid_values:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unsupported include values: {', '.join(sorted(invalid_values))}",
        )
    return values


@router.get("/items", response_model=CatalogItemsResponse)
async def list_items(
    request: Request,
    updated_after: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    site_id: int | None = Query(default=None),
    identity: Identity = Depends(require_user_identity),
    uow: UnitOfWork = Depends(get_uow),
) -> CatalogItemsResponse:
    async with uow:
        accessible_site_ids = await _resolve_accessible_site_ids(uow, identity)
        _require_catalog_read_access(identity, accessible_site_ids, site_id=site_id)
        items = await uow.catalog.list_items(updated_after=updated_after, limit=limit)

    next_updated_after = max((item.updated_at for item in items), default=None)
    logger.info("request_id=%s catalog_items returned=%s", get_request_id(request), len(items))
    return CatalogItemsResponse(items=items, server_time=datetime.now(UTC), next_updated_after=next_updated_after)


@router.get("/categories", response_model=CatalogCategoriesResponse)
async def list_categories(
    request: Request,
    updated_after: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    site_id: int | None = Query(default=None),
    identity: Identity = Depends(require_user_identity),
    uow: UnitOfWork = Depends(get_uow),
) -> CatalogCategoriesResponse:
    async with uow:
        accessible_site_ids = await _resolve_accessible_site_ids(uow, identity)
        _require_catalog_read_access(identity, accessible_site_ids, site_id=site_id)
        categories = await uow.catalog.list_categories(updated_after=updated_after, limit=limit)

    next_updated_after = max((category.updated_at for category in categories), default=None)
    logger.info("request_id=%s catalog_categories returned=%s", get_request_id(request), len(categories))
    return CatalogCategoriesResponse(
        categories=categories,
        server_time=datetime.now(UTC),
        next_updated_after=next_updated_after,
    )


@router.get("/units", response_model=CatalogUnitsResponse)
async def list_units(
    request: Request,
    updated_after: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    site_id: int | None = Query(default=None),
    identity: Identity = Depends(require_user_identity),
    uow: UnitOfWork = Depends(get_uow),
) -> CatalogUnitsResponse:
    async with uow:
        accessible_site_ids = await _resolve_accessible_site_ids(uow, identity)
        _require_catalog_read_access(identity, accessible_site_ids, site_id=site_id)
        units = await uow.catalog.list_units(updated_after=updated_after, limit=limit)

    next_updated_after = max((unit.updated_at for unit in units), default=None)
    logger.info("request_id=%s catalog_units returned=%s", get_request_id(request), len(units))
    return CatalogUnitsResponse(units=units, server_time=datetime.now(UTC), next_updated_after=next_updated_after)


@router.get("/sites", response_model=CatalogSitesResponse)
async def list_sites(
    request: Request,
    is_active: bool | None = Query(default=True),
    identity: Identity = Depends(require_user_identity),
    uow: UnitOfWork = Depends(get_uow),
) -> CatalogSitesResponse:
    async with uow:
        _require_catalog_read_access(identity, [])
        sites, _ = await uow.sites.list_sites(
            filter=SiteFilter(is_active=is_active),
            user_site_ids=None,
            page=1,
            page_size=1000,
        )
        scope_by_site_id = {}
        if not identity.has_global_business_access:
            scopes = list(await uow.user_access_scopes.list_user_scopes(identity.user_id))
            scope_by_site_id = {
                scope.site_id: scope
                for scope in scopes
                if scope.is_active
            }
        site_payload = []
        for site in sites:
            scope = scope_by_site_id.get(site.id)
            site_payload.append(
                {
                    "site_id": site.id,
                    "code": site.code,
                    "name": site.name,
                    "is_active": site.is_active,
                    "permissions": {
                        "can_view": True,
                        "can_operate": True
                        if identity.has_global_business_access
                        else bool(scope and scope.can_view and scope.can_operate),
                        "can_manage_catalog": True
                        if identity.has_global_business_access
                        else bool(scope and scope.can_view and scope.can_operate and scope.can_manage_catalog),
                    },
                }
            )

    logger.info("request_id=%s catalog_sites returned=%s", get_request_id(request), len(site_payload))
    return CatalogSitesResponse(sites=site_payload, server_time=datetime.now(UTC))


@router.get("/categories/tree", response_model=list[CategoryTreeNode])
async def get_categories_tree(
    request: Request,
    site_id: int | None = Query(default=None),
    identity: Identity = Depends(require_user_identity),
    uow: UnitOfWork = Depends(get_uow),
) -> list[CategoryTreeNode]:
    async with uow:
        accessible_site_ids = await _resolve_accessible_site_ids(uow, identity)
        _require_catalog_read_access(identity, accessible_site_ids, site_id=site_id)
        categories_tree = await uow.catalog.get_categories_tree()

    logger.info("request_id=%s catalog_categories_tree returned=%s", get_request_id(request), len(categories_tree))
    return [CategoryTreeNode.model_validate(node) for node in categories_tree]


async def _build_browse_categories_response(
    *,
    uow: UnitOfWork,
    search: str | None,
    parent_id: int | None,
    page: int,
    page_size: int,
    include: set[str],
    items_preview_limit: int,
) -> tuple[list[dict], int]:
    category_rows, total_count = await uow.catalog.list_categories_page(
        search=search,
        parent_id=parent_id,
        page=page,
        page_size=page_size,
    )
    category_ids = [int(row["id"]) for row in category_rows]

    preview_by_category = (
        await uow.catalog.list_items_preview(category_ids, items_preview_limit)
        if "items_preview" in include
        else {}
    )
    chain_by_category = (
        await uow.catalog.get_parent_chain_summaries(category_ids)
        if "parent_chain_summary" in include
        else {}
    )

    categories = []
    for row in category_rows:
        parent = None
        if "parent" in include and row["parent_ref_id"] is not None:
            parent = {
                "id": int(row["parent_ref_id"]),
                "name": row["parent_name"],
            }

        categories.append(
            {
                "id": int(row["id"]),
                "name": row["name"],
                "code": row["code"],
                "parent_id": row["parent_id"],
                "parent": parent,
                "parent_chain_summary": chain_by_category.get(int(row["id"]), []),
                "children_count": int(row["children_count"] or 0),
                "items_count": int(row["items_count"] or 0),
                "items_preview": preview_by_category.get(int(row["id"]), []),
                "is_active": row["is_active"],
                "updated_at": row["updated_at"],
                "sort_order": row["sort_order"],
            }
        )

    return categories, total_count


@router.get("/read/items", response_model=CatalogBrowseItemsResponse)
async def browse_items(
    request: Request,
    search: str | None = Query(default=None),
    category_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    site_id: int | None = Query(default=None),
    identity: Identity = Depends(require_user_identity),
    uow: UnitOfWork = Depends(get_uow),
) -> CatalogBrowseItemsResponse:
    async with uow:
        accessible_site_ids = await _resolve_accessible_site_ids(uow, identity)
        _require_catalog_read_access(identity, accessible_site_ids, site_id=site_id)
        items, total_count = await uow.catalog.list_items_page(
            search=search,
            category_id=category_id,
            page=page,
            page_size=page_size,
        )

    logger.info(
        "request_id=%s catalog_read_items returned=%s total=%s",
        get_request_id(request),
        len(items),
        total_count,
    )
    return CatalogBrowseItemsResponse(
        items=items,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/read/categories", response_model=CatalogBrowseCategoriesResponse)
async def browse_categories(
    request: Request,
    search: str | None = Query(default=None),
    parent_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    include: str | None = Query(default=None),
    items_preview_limit: int = Query(default=5, ge=1, le=20),
    site_id: int | None = Query(default=None),
    identity: Identity = Depends(require_user_identity),
    uow: UnitOfWork = Depends(get_uow),
) -> CatalogBrowseCategoriesResponse:
    include_values = _parse_category_read_includes(include)

    async with uow:
        accessible_site_ids = await _resolve_accessible_site_ids(uow, identity)
        _require_catalog_read_access(identity, accessible_site_ids, site_id=site_id)
        categories, total_count = await _build_browse_categories_response(
            uow=uow,
            search=search,
            parent_id=parent_id,
            page=page,
            page_size=page_size,
            include=include_values,
            items_preview_limit=items_preview_limit,
        )

    logger.info(
        "request_id=%s catalog_read_categories returned=%s total=%s",
        get_request_id(request),
        len(categories),
        total_count,
    )
    return CatalogBrowseCategoriesResponse(
        categories=categories,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/read/categories/{category_id}/items", response_model=CatalogBrowseItemsResponse)
async def browse_category_items(
    category_id: int,
    request: Request,
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    site_id: int | None = Query(default=None),
    identity: Identity = Depends(require_user_identity),
    uow: UnitOfWork = Depends(get_uow),
) -> CatalogBrowseItemsResponse:
    async with uow:
        accessible_site_ids = await _resolve_accessible_site_ids(uow, identity)
        _require_catalog_read_access(identity, accessible_site_ids, site_id=site_id)
        category = await uow.catalog.get_category_by_id(category_id)
        if category is None or not category.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="category not found")

        items, total_count = await uow.catalog.list_items_page(
            search=search,
            category_id=category_id,
            page=page,
            page_size=page_size,
        )

    logger.info(
        "request_id=%s catalog_read_category_items category_id=%s returned=%s total=%s",
        get_request_id(request),
        category_id,
        len(items),
        total_count,
    )
    return CatalogBrowseItemsResponse(
        items=items,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/read/categories/{category_id}/children", response_model=CatalogBrowseCategoriesResponse)
async def browse_category_children(
    category_id: int,
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    include: str | None = Query(default=None),
    items_preview_limit: int = Query(default=5, ge=1, le=20),
    site_id: int | None = Query(default=None),
    identity: Identity = Depends(require_user_identity),
    uow: UnitOfWork = Depends(get_uow),
) -> CatalogBrowseCategoriesResponse:
    include_values = _parse_category_read_includes(include)

    async with uow:
        accessible_site_ids = await _resolve_accessible_site_ids(uow, identity)
        _require_catalog_read_access(identity, accessible_site_ids, site_id=site_id)
        category = await uow.catalog.get_category_by_id(category_id)
        if category is None or not category.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="category not found")

        categories, total_count = await _build_browse_categories_response(
            uow=uow,
            search=None,
            parent_id=category_id,
            page=page,
            page_size=page_size,
            include=include_values,
            items_preview_limit=items_preview_limit,
        )

    logger.info(
        "request_id=%s catalog_read_category_children category_id=%s returned=%s total=%s",
        get_request_id(request),
        category_id,
        len(categories),
        total_count,
    )
    return CatalogBrowseCategoriesResponse(
        categories=categories,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/read/categories/{category_id}/parent-chain", response_model=CategoryParentChainResponse)
async def browse_category_parent_chain(
    category_id: int,
    request: Request,
    site_id: int | None = Query(default=None),
    identity: Identity = Depends(require_user_identity),
    uow: UnitOfWork = Depends(get_uow),
) -> CategoryParentChainResponse:
    async with uow:
        accessible_site_ids = await _resolve_accessible_site_ids(uow, identity)
        _require_catalog_read_access(identity, accessible_site_ids, site_id=site_id)
        category = await uow.catalog.get_category_by_id(category_id)
        if category is None or not category.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="category not found")

        chain_by_category = await uow.catalog.get_parent_chain_summaries([category_id])

    logger.info(
        "request_id=%s catalog_read_category_parent_chain category_id=%s chain_length=%s",
        get_request_id(request),
        category_id,
        len(chain_by_category.get(category_id, [])),
    )
    return CategoryParentChainResponse(
        category_id=category_id,
        parent_chain_summary=chain_by_category.get(category_id, []),
    )
