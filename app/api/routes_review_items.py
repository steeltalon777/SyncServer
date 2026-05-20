from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from app.api.deps import get_uow, require_user_identity
from app.core.identity import Identity
from app.models.site import Site
from app.schemas.operation import OperationListResponse
from app.schemas.review_item import (
    ReviewItemConfirmRequest,
    ReviewItemDetailResponse,
    ReviewItemListResponse,
    ReviewItemMergeRequest,
    ReviewItemResponse,
    ReviewItemBalanceDto,
)
from app.services.operations_policy import OperationsPolicy
from app.services.review_items_service import ReviewItemsService
from app.services.uow import UnitOfWork
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

router = APIRouter(prefix="/review-items", tags=["review-items"])


def _build_review_item_response(item, category=None, unit=None) -> ReviewItemResponse:
    """Build a ReviewItemResponse from an Item ORM entity."""
    cat = category or getattr(item, "category", None)
    u = unit or getattr(item, "unit", None)
    return ReviewItemResponse(
        id=item.id,
        item_name=item.name,
        sku=item.sku,
        category_id=item.category_id,
        category_name=None if cat is None else cat.name,
        unit_id=item.unit_id,
        unit_name=None if u is None else u.name,
        unit_symbol=None if u is None else u.symbol,
        description=item.description,
        hashtags=item.hashtags,
        is_active=item.is_active,
        requires_review=item.requires_review,
        review_status=item.review_status,
        review_created_by_user_id=item.review_created_by_user_id,
        review_resolved_by_user_id=item.review_resolved_by_user_id,
        review_resolved_at=item.review_resolved_at,
        review_note=item.review_note,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("", response_model=ReviewItemListResponse)
async def list_review_items(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    search: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    created_by_user_id: UUID | None = Query(default=None),
    created_after: datetime | None = Query(default=None),
    created_before: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> ReviewItemListResponse:
    OperationsPolicy.require_temporary_item_moderation(identity, site_id=identity.default_site_id)
    async with uow:
        items, total_count = await uow.catalog.list_review_items_page(
            search=search,
            review_status=review_status,
            created_by_user_id=created_by_user_id,
            page=page,
            page_size=page_size,
        )

    return ReviewItemListResponse(
        items=[_build_review_item_response(item) for item in items],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/{item_id}", response_model=ReviewItemDetailResponse)
async def get_review_item(
    item_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> ReviewItemDetailResponse:
    OperationsPolicy.require_temporary_item_moderation(identity, site_id=identity.default_site_id)
    async with uow:
        item = await uow.catalog.get_item_by_id(item_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review item not found")
        if not item.requires_review:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item does not require review")

        # Get balances per site
        balances_per_site: list[ReviewItemBalanceDto] = []
        subject = await uow.inventory_subjects.get_by_item_id(item_id)
        if subject is not None:
            balances = await uow.balances.get_all_by_inventory_subject(int(subject.id))
            site_ids = {int(b.site_id) for b in balances if b.qty != 0}
            if site_ids:
                stmt = select(Site).where(Site.id.in_(site_ids))
                result = await uow.session.execute(stmt)
                sites = {s.id: s.name for s in result.scalars().all()}
            else:
                sites = {}
            for br in balances:
                if br.qty != 0:
                    balances_per_site.append(
                        ReviewItemBalanceDto(
                            site_id=int(br.site_id),
                            site_name=sites.get(int(br.site_id)),
                            qty=int(br.qty),
                        )
                    )

        # Count operations referencing this item
        operations_count = await uow.operations.count_operations_by_item_id(item_id)

        category = await uow.catalog.get_category_by_id(item.category_id)
        unit = await uow.catalog.get_unit_by_id(item.unit_id)

    resp = _build_review_item_response(item, category=category, unit=unit)
    return ReviewItemDetailResponse(
        **resp.model_dump(),
        balances_per_site=balances_per_site,
        operations_count=operations_count,
    )


@router.get("/{item_id}/operations", response_model=OperationListResponse)
async def list_review_item_operations(
    item_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> OperationListResponse:
    OperationsPolicy.require_temporary_item_moderation(identity, site_id=identity.default_site_id)
    async with uow:
        item = await uow.catalog.get_item_by_id(item_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review item not found")

        operations, total_count = await uow.operations.get_operations_by_item_id(
            item_id=item_id,
            page=page,
            page_size=page_size,
        )

    return OperationListResponse(
        items=operations,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.post("/{item_id}/confirm", response_model=ReviewItemResponse)
async def confirm_review_item(
    item_id: int,
    payload: ReviewItemConfirmRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> ReviewItemResponse:
    OperationsPolicy.require_temporary_item_moderation(identity, site_id=identity.default_site_id)
    if identity.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User authentication required")
    service = ReviewItemsService()
    async with uow:
        await service.confirm_review_item(
            uow,
            item_id=item_id,
            resolved_by_user_id=identity.user_id,
            payload=payload,
        )
        item = await uow.catalog.get_item_by_id(item_id)
    return _build_review_item_response(item)


@router.post("/{item_id}/merge", response_model=ReviewItemResponse)
async def merge_review_item(
    item_id: int,
    payload: ReviewItemMergeRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> ReviewItemResponse:
    OperationsPolicy.require_temporary_item_moderation(identity, site_id=identity.default_site_id)
    if identity.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User authentication required")
    service = ReviewItemsService()
    async with uow:
        await service.merge_review_item(
            uow,
            item_id=item_id,
            target_item_id=payload.target_item_id,
            resolved_by_user_id=identity.user_id,
            resolution_note=payload.comment,
        )
        item = await uow.catalog.get_item_by_id(item_id)
    return _build_review_item_response(item)


@router.delete("/{item_id}", response_model=ReviewItemResponse)
async def delete_review_item(
    item_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> ReviewItemResponse:
    OperationsPolicy.require_temporary_item_moderation(identity, site_id=identity.default_site_id)
    if identity.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User authentication required")
    service = ReviewItemsService()
    async with uow:
        await service.delete_review_item(
            uow,
            item_id=item_id,
            resolved_by_user_id=identity.user_id,
            resolution_note="Удалён пользователем",
        )
        item = await uow.catalog.get_item_by_id(item_id)
    return _build_review_item_response(item)
