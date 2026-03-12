from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request

from app.api.deps import (
    get_request_id,
    get_uow,
    require_service_auth,
    require_acting_user,
)
from app.schemas.balance import BalanceFilter, BalanceListResponse, BalanceResponse
from app.services.access_service import AccessService
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/balances")
logger = logging.getLogger(__name__)


@router.get("", response_model=BalanceListResponse)
async def list_balances(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
    site_id: UUID | None = Query(None, description="Filter by site ID"),
    item_id: int | None = Query(None, description="Filter by item ID"),
    category_id: int | None = Query(None, description="Filter by category ID"),
    search: str | None = Query(None, description="Search in item name, SKU, or description"),
    only_positive: bool = Query(False, description="Show only positive balances"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=200, description="Page size"),
) -> BalanceListResponse:
    """List balances with filtering."""
    # Validate service authentication
    await require_service_auth(request=request, authorization=authorization)
    
    # Validate acting user context
    user_context = await require_acting_user(
        request=request,
        uow=uow,
        x_acting_user_id=x_acting_user_id,
        x_acting_site_id=x_acting_site_id,
    )
    
    # Get user's sites and roles
    user_sites_roles = await AccessService.get_user_sites_with_roles(uow, user_context["user_id"])
    user_site_ids = [site_id for site_id, _ in user_sites_roles]
    
    # Build filter
    filter_data = BalanceFilter(
        site_id=site_id,
        item_id=item_id,
        category_id=category_id,
        search=search,
        only_positive=only_positive,
    )
    
    async with uow:
        balances, total_count = await uow.balances.list_balances(
            filter=filter_data,
            user_site_ids=user_site_ids,
            page=page,
            page_size=page_size,
        )
    
    # Convert to response models
    balance_responses = [
        BalanceResponse(
            site_id=balance.site_id,
            item_id=balance.item_id,
            quantity=balance.qty,
            updated_at=balance.updated_at.isoformat(),
        )
        for balance in balances
    ]
    
    logger.info(
        "request_id=%s list_balances user_id=%s site_id=%s returned=%s total=%s",
        get_request_id(request),
        user_context["user_id"],
        user_context["site_id"],
        len(balance_responses),
        total_count,
    )
    
    return BalanceListResponse(
        balances=balance_responses,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/by-site", response_model=BalanceListResponse)
async def get_balances_by_site(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
    site_id: UUID = Query(..., description="Site ID"),
    only_positive: bool = Query(False, description="Show only positive balances"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=200, description="Page size"),
) -> BalanceListResponse:
    """Get balances for a specific site."""
    # Validate service authentication
    await require_service_auth(request=request, authorization=authorization)
    
    # Validate acting user context
    user_context = await require_acting_user(
        request=request,
        uow=uow,
        x_acting_user_id=x_acting_user_id,
        x_acting_site_id=x_acting_site_id,
    )
    
    # Check if user has access to the requested site
    user_sites_roles = await AccessService.get_user_sites_with_roles(uow, user_context["user_id"])
    user_site_ids = [site_id for site_id, _ in user_sites_roles]
    
    if site_id not in user_site_ids:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to this site",
        )
    
    # Build filter
    filter_data = BalanceFilter(
        site_id=site_id,
        only_positive=only_positive,
    )
    
    async with uow:
        balances, total_count = await uow.balances.list_balances(
            filter=filter_data,
            user_site_ids=[site_id],  # Only this site
            page=page,
            page_size=page_size,
        )
    
    # Convert to response models
    balance_responses = [
        BalanceResponse(
            site_id=balance.site_id,
            item_id=balance.item_id,
            quantity=balance.qty,
            updated_at=balance.updated_at.isoformat(),
        )
        for balance in balances
    ]
    
    logger.info(
        "request_id=%s get_balances_by_site user_id=%s site_id=%s returned=%s total=%s",
        get_request_id(request),
        user_context["user_id"],
        site_id,
        len(balance_responses),
        total_count,
    )
    
    return BalanceListResponse(
        balances=balance_responses,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/summary")
async def get_balances_summary(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> dict:
    """Get balances summary for user's accessible sites."""
    # Validate service authentication
    await require_service_auth(request=request, authorization=authorization)
    
    # Validate acting user context
    user_context = await require_acting_user(
        request=request,
        uow=uow,
        x_acting_user_id=x_acting_user_id,
        x_acting_site_id=x_acting_site_id,
    )
    
    # Get user's sites and roles
    user_sites_roles = await AccessService.get_user_sites_with_roles(uow, user_context["user_id"])
    user_site_ids = [site_id for site_id, _ in user_sites_roles]
    
    async with uow:
        summary = await uow.balances.get_balances_summary(user_site_ids)
    
    logger.info(
        "request_id=%s get_balances_summary user_id=%s sites=%s summary=%s",
        get_request_id(request),
        user_context["user_id"],
        len(user_site_ids),
        summary,
    )
    
    return {
        "user_id": user_context["user_id"],
        "accessible_sites_count": len(user_site_ids),
        "summary": summary,
    }