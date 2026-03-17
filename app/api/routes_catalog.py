from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import (
    auth_catalog_headers,
    get_request_id,
    get_uow,
    require_device_auth,
    require_user_token_auth,
)
from app.core.identity import Identity
from app.schemas.admin import SiteFilter
from app.schemas.catalog import (
    CatalogCategoriesResponse,
    CatalogItemsResponse,
    CatalogRequest,
    CatalogSitesResponse,
    CatalogUnitsResponse,
    CategoryTreeNode,
)
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/catalog")
logger = logging.getLogger(__name__)

ALLOWED_CATALOG_READ_ROLES = {"chief_storekeeper", "storekeeper", "observer"}


async def _resolve_accessible_site_ids(uow: UnitOfWork, identity: Identity) -> list[int]:
    if identity.is_root:
        sites, _ = await uow.sites.list_sites(
            filter=SiteFilter(is_active=True),
            user_site_ids=None,
            page=1,
            page_size=1000,
        )
        return [site.id for site in sites]

    scopes = list(await uow.user_access_scopes.list_user_scopes(identity.user_id))
    return [scope.site_id for scope in scopes if scope.is_active and scope.can_view]


def _require_catalog_read_access(identity: Identity, accessible_site_ids: list[int], site_id: int | None = None) -> None:
    if identity.is_root:
        return
    if identity.role not in ALLOWED_CATALOG_READ_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="catalog read access denied",
        )
    if not accessible_site_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="catalog read access denied",
        )
    if site_id is not None and site_id not in accessible_site_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="no access to requested site",
        )


@router.get("/items", response_model=CatalogItemsResponse)
async def list_items(
    request: Request,
    updated_after: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    site_id: int | None = Query(default=None),
    identity: Identity = Depends(require_user_token_auth),
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
    identity: Identity = Depends(require_user_token_auth),
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
    identity: Identity = Depends(require_user_token_auth),
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
    identity: Identity = Depends(require_user_token_auth),
    uow: UnitOfWork = Depends(get_uow),
) -> CatalogSitesResponse:
    async with uow:
        if identity.is_root:
            sites, _ = await uow.sites.list_sites(
                filter=SiteFilter(is_active=is_active),
                user_site_ids=None,
                page=1,
                page_size=1000,
            )
            site_payload = [
                {
                    "site_id": site.id,
                    "code": site.code,
                    "name": site.name,
                    "is_active": site.is_active,
                    "permissions": {
                        "can_view": True,
                        "can_operate": True,
                        "can_manage_catalog": True,
                    },
                }
                for site in sites
            ]
        else:
            if identity.role not in ALLOWED_CATALOG_READ_ROLES:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="catalog read access denied",
                )

            scopes = list(await uow.user_access_scopes.list_user_scopes(identity.user_id))
            scope_by_site_id = {
                scope.site_id: scope
                for scope in scopes
                if scope.is_active and scope.can_view
            }
            site_ids = list(scope_by_site_id.keys())
            if not site_ids:
                site_payload = []
            else:
                sites, _ = await uow.sites.list_sites(
                    filter=SiteFilter(is_active=is_active),
                    user_site_ids=site_ids,
                    page=1,
                    page_size=1000,
                )
                site_payload = [
                    {
                        "site_id": site.id,
                        "code": site.code,
                        "name": site.name,
                        "is_active": site.is_active,
                        "permissions": {
                            "can_view": scope_by_site_id[site.id].can_view,
                            "can_operate": scope_by_site_id[site.id].can_operate,
                            "can_manage_catalog": scope_by_site_id[site.id].can_manage_catalog,
                        },
                    }
                    for site in sites
                ]

    logger.info("request_id=%s catalog_sites returned=%s", get_request_id(request), len(site_payload))
    return CatalogSitesResponse(sites=site_payload, server_time=datetime.now(UTC))


@router.get("/categories/tree", response_model=list[CategoryTreeNode])
async def get_categories_tree(
    request: Request,
    site_id: int | None = Query(default=None),
    identity: Identity = Depends(require_user_token_auth),
    uow: UnitOfWork = Depends(get_uow),
) -> list[CategoryTreeNode]:
    async with uow:
        accessible_site_ids = await _resolve_accessible_site_ids(uow, identity)
        _require_catalog_read_access(identity, accessible_site_ids, site_id=site_id)
        categories_tree = await uow.catalog.get_categories_tree()

    logger.info("request_id=%s catalog_categories_tree returned=%s", get_request_id(request), len(categories_tree))
    return [CategoryTreeNode.model_validate(node) for node in categories_tree]


# -----------------------------------------------------------------------------
# LEGACY COMPATIBILITY READ ENDPOINTS (POST + device auth)
# -----------------------------------------------------------------------------
@router.post("/items", response_model=CatalogItemsResponse)
async def list_items_legacy(
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
    logger.info("request_id=%s catalog_items_legacy returned=%s", get_request_id(request), len(items))
    return CatalogItemsResponse(items=items, server_time=datetime.now(UTC), next_updated_after=next_updated_after)


@router.post("/categories", response_model=CatalogCategoriesResponse)
async def list_categories_legacy(
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
    logger.info("request_id=%s catalog_categories_legacy returned=%s", get_request_id(request), len(categories))
    return CatalogCategoriesResponse(
        categories=categories,
        server_time=datetime.now(UTC),
        next_updated_after=next_updated_after,
    )


@router.post("/units", response_model=CatalogUnitsResponse)
async def list_units_legacy(
    payload: CatalogRequest,
    request: Request,
    auth: dict = Depends(auth_catalog_headers),
    uow: UnitOfWork = Depends(get_uow),
) -> CatalogUnitsResponse:
    async with uow:
        await require_device_auth(
            request=request,
            uow=uow,
            site_id=auth["site_id"],
            device_id=auth["device_id"],
            device_token=auth["device_token"],
            client_version=auth["client_version"],
        )
        units = await uow.catalog.list_units(updated_after=payload.updated_after, limit=payload.limit)

    next_updated_after = max((unit.updated_at for unit in units), default=None)
    logger.info("request_id=%s catalog_units_legacy returned=%s", get_request_id(request), len(units))
    return CatalogUnitsResponse(units=units, server_time=datetime.now(UTC), next_updated_after=next_updated_after)
