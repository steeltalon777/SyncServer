from __future__ import annotations

import structlog

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import get_request_id, get_uow, require_user_identity
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
logger = structlog.get_logger()

# ADR-0030: agent has observer-level read access to balances.
READ_ROLES = {"chief_storekeeper", "storekeeper", "observer", "agent"}


def _require_read_access(identity: Identity) -> None:
    if identity.has_global_business_access:
        return
    if identity.role not in READ_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="read balances permission required",
        )


async def _resolve_visible_site_ids(uow: UnitOfWork, identity: Identity) -> list[int]:
    if identity.has_global_business_access or identity.role in READ_ROLES:
        sites, _ = await uow.sites.list_sites(
            filter=SiteFilter(is_active=True),
            user_site_ids=None,
            page=1,
            page_size=1000,
        )
        return [site.id for site in sites]
    return []


@router.get("", response_model=BalanceListResponse)
async def list_balances(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    site_id: int | None = Query(None, description="Filter by site ID"),
    item_id: int | None = Query(None, description="Filter by item ID"),
    item_ids: str | None = Query(None, description="Targeted item IDs (comma-separated, max 200)"),
    category_id: int | None = Query(None, description="Filter by category ID"),
    search: str | None = Query(None, description="Search in item fields"),
    only_positive: bool = Query(False, description="Show only positive balances"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=200, description="Page size"),
) -> BalanceListResponse:
    _require_read_access(identity)

    parsed_item_ids = None
    if item_ids is not None:
        try:
            parsed_item_ids = list(dict.fromkeys(int(x.strip()) for x in item_ids.split(",") if x.strip()))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="item_ids must be comma-separated integers",
            )
        if not parsed_item_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="item_ids must not be empty",
            )
        if len(parsed_item_ids) > 200:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="item_ids must not exceed 200 entries",
            )
        # Reject incompatible filters with targeted semantics
        if search is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="search filter is incompatible with targeted item_ids",
            )
        if only_positive:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="only_positive filter is incompatible with targeted item_ids",
            )
        if category_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="category_id filter is incompatible with targeted item_ids",
            )

    async with uow:
        visible_site_ids = await _resolve_visible_site_ids(uow, identity)

        filter_data = BalanceFilter(
            site_id=site_id,
            item_id=item_id,
            item_ids=parsed_item_ids,
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
        "list_balances",
        request_id=get_request_id(request),
        user_id=identity.user_id,
        returned=len(items),
        total=total_count,
        targeted=bool(parsed_item_ids),
    )
    return BalanceListResponse(
        items=items,
        total_count=total_count,
        page=page if not parsed_item_ids else 1,
        page_size=page_size if not parsed_item_ids else total_count,
    )


@router.get("/by-site", response_model=BalanceListResponse)
async def list_balances_by_site(
    request: Request,
    site_id: int = Query(..., description="Site ID"),
    only_positive: bool = Query(False, description="Show only positive balances"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=200, description="Page size"),
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> BalanceListResponse:
    return await list_balances(
        request=request,
        uow=uow,
        identity=identity,
        site_id=site_id,
        item_id=None,
        item_ids=None,
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
    identity: Identity = Depends(require_user_identity),
) -> BalanceSummaryResponse:
    _require_read_access(identity)

    async with uow:
        visible_site_ids = await _resolve_visible_site_ids(uow, identity)
        summary = await uow.balances.get_balances_summary(visible_site_ids)

    logger.info(
        "balances_summary",
        request_id=get_request_id(request),
        user_id=identity.user_id,
        sites=len(visible_site_ids),
    )
    return BalanceSummaryResponse(
        accessible_sites_count=len(visible_site_ids),
        summary=summary,
    )
