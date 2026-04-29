from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import get_request_id, get_uow, require_user_identity
from app.core.identity import Identity
from app.schemas.admin import SiteFilter
from app.schemas.report import (
    ItemMovementFilter,
    ItemMovementReportResponse,
    ItemMovementRow,
    StockSummaryFilter,
    StockSummaryReportResponse,
    StockSummaryRow,
)
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/reports")
logger = logging.getLogger(__name__)

def _require_read_access(identity: Identity) -> None:
    if identity.user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="read reports permission required",
        )


async def _resolve_visible_site_ids(uow: UnitOfWork, identity: Identity) -> list[int]:
    if identity.user is None:
        return []

    sites, _ = await uow.sites.list_sites(
        filter=SiteFilter(is_active=None),
        user_site_ids=None,
        page=1,
        page_size=1000,
    )
    return [site.id for site in sites]


@router.get("/item-movement", response_model=ItemMovementReportResponse)
async def list_item_movement_report(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    site_id: int | None = Query(None, description="Filter by site ID"),
    item_id: int | None = Query(None, description="Filter by item ID"),
    category_id: int | None = Query(None, description="Filter by category ID"),
    search: str | None = Query(None, description="Search in item, category, or site labels"),
    date_from: datetime | None = Query(None, description="Inclusive report start datetime"),
    date_to: datetime | None = Query(None, description="Inclusive report end datetime"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=200, description="Page size"),
) -> ItemMovementReportResponse:
    _require_read_access(identity)
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="date_from must be less than or equal to date_to",
        )

    async with uow:
        visible_site_ids = await _resolve_visible_site_ids(uow, identity)
        if site_id is not None and site_id not in visible_site_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="requested site not found",
            )

        filter_data = ItemMovementFilter(
            site_id=site_id,
            item_id=item_id,
            category_id=category_id,
            search=search,
            date_from=date_from,
            date_to=date_to,
        )
        items, total_count = await uow.reports.list_item_movement(
            filter=filter_data,
            user_site_ids=visible_site_ids,
            page=page,
            page_size=page_size,
        )

    logger.info(
        "request_id=%s item_movement_report user_id=%s returned=%s total=%s",
        get_request_id(request),
        identity.user_id,
        len(items),
        total_count,
    )
    return ItemMovementReportResponse(
        items=[ItemMovementRow.model_validate(item) for item in items],
        total_count=total_count,
        page=page,
        page_size=page_size,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/stock-summary", response_model=StockSummaryReportResponse)
async def list_stock_summary_report(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    site_id: int | None = Query(None, description="Filter by site ID"),
    category_id: int | None = Query(None, description="Filter by category ID"),
    search: str | None = Query(None, description="Search in item, category, or site labels"),
    only_positive: bool = Query(False, description="Show only positive balances"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=200, description="Page size"),
) -> StockSummaryReportResponse:
    _require_read_access(identity)

    async with uow:
        visible_site_ids = await _resolve_visible_site_ids(uow, identity)
        if site_id is not None and site_id not in visible_site_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="requested site not found",
            )

        filter_data = StockSummaryFilter(
            site_id=site_id,
            category_id=category_id,
            search=search,
            only_positive=only_positive,
        )
        items, total_count = await uow.reports.list_stock_summary(
            filter=filter_data,
            user_site_ids=visible_site_ids,
            page=page,
            page_size=page_size,
        )

    logger.info(
        "request_id=%s stock_summary_report user_id=%s returned=%s total=%s",
        get_request_id(request),
        identity.user_id,
        len(items),
        total_count,
    )
    return StockSummaryReportResponse(
        items=[StockSummaryRow.model_validate(item) for item in items],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )
