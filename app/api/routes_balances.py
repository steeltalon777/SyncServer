from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import get_request_id, get_uow, require_user_token_auth
from app.core.identity import Identity
from app.schemas.admin import SiteFilter
from app.schemas.balance import (
    BalanceFilter,
    BalanceListResponse,
    BalanceResponse,
    BalanceSummaryResponse,
)
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/balances")
logger = logging.getLogger(__name__)

READ_ROLES = {"chief_storekeeper", "storekeeper", "observer"}


def _require_read_access(identity: Identity) -> None:
    if identity.has_global_business_access:
        return
    if identity.role not in READ_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="read balances permission required",
        )


async def _resolve_visible_site_ids(uow: UnitOfWork, identity: Identity) -> list[int]:
    if identity.has_global_business_access:
        sites, _ = await uow.sites.list_sites(
            filter=SiteFilter(is_active=None),
            user_site_ids=None,
            page=1,
            page_size=1000,
        )
        return [site.id for site in sites]

    scopes = list(await uow.user_access_scopes.list_user_scopes(identity.user_id))
    return [scope.site_id for scope in scopes if scope.is_active and scope.can_view]


@router.get("", response_model=BalanceListResponse)
async def list_balances(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_token_auth),
    site_id: int | None = Query(None, description="Filter by site ID"),
    item_id: int | None = Query(None, description="Filter by item ID"),
    category_id: int | None = Query(None, description="Filter by category ID"),
    search: str | None = Query(None, description="Search in item fields"),
    only_positive: bool = Query(False, description="Show only positive balances"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=200, description="Page size"),
) -> BalanceListResponse:
    _require_read_access(identity)

    async with uow:
        visible_site_ids = await _resolve_visible_site_ids(uow, identity)
        if site_id is not None and site_id not in visible_site_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="user does not have access to requested site",
            )

        filter_data = BalanceFilter(
            site_id=site_id,
            item_id=item_id,
            category_id=category_id,
            search=search,
            only_positive=only_positive,
        )
        balances, total_count = await uow.balances.list_balances(
            filter=filter_data,
            user_site_ids=visible_site_ids,
            page=page,
            page_size=page_size,
        )

    items = [BalanceResponse.model_validate(balance) for balance in balances]
    logger.info(
        "request_id=%s list_balances user_id=%s returned=%s total=%s",
        get_request_id(request),
        identity.user_id,
        len(items),
        total_count,
    )
    return BalanceListResponse(
        items=items,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/by-site", response_model=BalanceListResponse)
async def list_balances_by_site(
    request: Request,
    site_id: int = Query(..., description="Site ID"),
    only_positive: bool = Query(False, description="Show only positive balances"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=200, description="Page size"),
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_token_auth),
) -> BalanceListResponse:
    return await list_balances(
        request=request,
        uow=uow,
        identity=identity,
        site_id=site_id,
        item_id=None,
        category_id=None,
        search=None,
        only_positive=only_positive,
        page=page,
        page_size=page_size,
    )


@router.get("/summary", response_model=BalanceSummaryResponse)
async def get_balances_summary(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_token_auth),
) -> BalanceSummaryResponse:
    _require_read_access(identity)

    async with uow:
        visible_site_ids = await _resolve_visible_site_ids(uow, identity)
        summary = await uow.balances.get_balances_summary(visible_site_ids)

    logger.info(
        "request_id=%s balances_summary user_id=%s sites=%s",
        get_request_id(request),
        identity.user_id,
        len(visible_site_ids),
    )
    return BalanceSummaryResponse(
        accessible_sites_count=len(visible_site_ids),
        summary=summary,
    )
