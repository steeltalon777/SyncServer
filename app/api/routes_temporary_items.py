from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import get_uow, require_user_identity
from app.core.identity import Identity
from app.schemas.temporary_item import TemporaryItemListResponse, TemporaryItemMergeRequest, TemporaryItemResponse
from app.schemas.temporary_item_views import build_temporary_item_response
from app.services.operations_policy import OperationsPolicy
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/temporary-items", tags=["temporary-items"])


@router.get("", response_model=TemporaryItemListResponse)
async def list_temporary_items(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    created_by_user_id: UUID | None = Query(default=None),
    resolved_item_id: int | None = Query(default=None),
    created_after: datetime | None = Query(default=None),
    created_before: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> TemporaryItemListResponse:
    OperationsPolicy.require_temporary_item_moderation(identity, site_id=identity.default_site_id)
    async with uow:
        items, total_count = await uow.temporary_items.list_items(
            status=status_filter,
            search=search,
            created_by_user_id=created_by_user_id,
            resolved_item_id=resolved_item_id,
            created_after=created_after,
            created_before=created_before,
            page=page,
            page_size=page_size,
        )
    return TemporaryItemListResponse(
        items=[build_temporary_item_response(item) for item in items],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/{temporary_item_id}", response_model=TemporaryItemResponse)
async def get_temporary_item(
    temporary_item_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> TemporaryItemResponse:
    OperationsPolicy.require_temporary_item_moderation(identity, site_id=identity.default_site_id)
    async with uow:
        item = await uow.temporary_items.get_by_id(temporary_item_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="temporary item not found")
    return build_temporary_item_response(item)


@router.post("/{temporary_item_id}/approve-as-item", response_model=TemporaryItemResponse)
async def approve_temporary_item(
    temporary_item_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> TemporaryItemResponse:
    OperationsPolicy.require_temporary_item_moderation(identity, site_id=identity.default_site_id)
    async with uow:
        item = await uow.temporary_items.get_by_id(temporary_item_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="temporary item not found")
        if item.status != "active":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="temporary item is already resolved")
        backing_item = await uow.catalog.get_item_by_id(item.item_id)
        if backing_item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="backing item not found")
        backing_item.is_active = True
        item = await uow.temporary_items.resolve_as_item(
            temporary_item_id=temporary_item_id,
            resolved_item_id=item.item_id,
            resolved_by_user_id=identity.user_id,
            resolution_type="approve_as_item",
            resolution_note="Phase 1 approve: backing catalog item activated",
        )
        item = await uow.temporary_items.get_by_id(temporary_item_id)
    return build_temporary_item_response(item)


@router.post("/{temporary_item_id}/merge", response_model=TemporaryItemResponse)
async def merge_temporary_item(
    temporary_item_id: int,
    payload: TemporaryItemMergeRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> TemporaryItemResponse:
    OperationsPolicy.require_temporary_item_moderation(identity, site_id=identity.default_site_id)
    async with uow:
        item = await uow.temporary_items.get_by_id(temporary_item_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="temporary item not found")
        if item.status != "active":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="temporary item is already resolved")
        target_item = await uow.catalog.get_item_by_id(payload.target_item_id)
        if target_item is None or target_item.deleted_at is not None or not target_item.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target item not found")
        if payload.target_item_id == item.item_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="target item must differ from backing item")
        item = await uow.temporary_items.merge_to_item(
            temporary_item_id=temporary_item_id,
            target_item_id=payload.target_item_id,
            resolved_by_user_id=identity.user_id,
            resolution_note=payload.comment,
        )
        item = await uow.temporary_items.get_by_id(temporary_item_id)
    return build_temporary_item_response(item)
