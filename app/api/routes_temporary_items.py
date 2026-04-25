from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.api.deps import get_uow, require_user_identity
from app.core.identity import Identity
from app.schemas.operation import OperationListResponse
from app.schemas.temporary_item import (
    TemporaryItemListResponse,
    TemporaryItemMergeRequest,
    TemporaryItemResponse,
)
from app.schemas.temporary_item_views import build_temporary_item_response
from app.services.operations_policy import OperationsPolicy
from app.services.temporary_items_resolution_service import (
    TemporaryItemsResolutionService,
)
from app.services.uow import UnitOfWork
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

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
    if identity.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User authentication required")
    async with uow:
        await TemporaryItemsResolutionService.approve_as_item(
            uow,
            temporary_item_id=temporary_item_id,
            resolved_by_user_id=identity.user_id,
        )
        item = await uow.temporary_items.get_by_id(temporary_item_id)
    return build_temporary_item_response(item)


@router.get("/{temporary_item_id}/operations", response_model=OperationListResponse)
async def list_temporary_item_operations(
    temporary_item_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> OperationListResponse:
    OperationsPolicy.require_temporary_item_moderation(identity, site_id=identity.default_site_id)
    async with uow:
        # Verify temporary item exists
        item = await uow.temporary_items.get_by_id(temporary_item_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="temporary item not found")
        operations, total_count = await uow.operations.get_operations_by_temporary_item_id(
            temporary_item_id=temporary_item_id,
            page=page,
            page_size=page_size,
        )
    return OperationListResponse(
        items=operations,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.post("/{temporary_item_id}/merge", response_model=TemporaryItemResponse)
async def merge_temporary_item(
    temporary_item_id: int,
    payload: TemporaryItemMergeRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> TemporaryItemResponse:
    OperationsPolicy.require_temporary_item_moderation(identity, site_id=identity.default_site_id)
    if identity.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User authentication required")
    async with uow:
        await TemporaryItemsResolutionService.merge_to_item(
            uow,
            temporary_item_id=temporary_item_id,
            target_item_id=payload.target_item_id,
            resolved_by_user_id=identity.user_id,
            resolution_note=payload.comment,
        )
        item = await uow.temporary_items.get_by_id(temporary_item_id)
    return build_temporary_item_response(item)


@router.delete("/{temporary_item_id}", response_model=TemporaryItemResponse)
async def delete_temporary_item(
    temporary_item_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> TemporaryItemResponse:
    """Удалить временный ТМЦ (мягкое удаление)."""
    OperationsPolicy.require_temporary_item_moderation(identity, site_id=identity.default_site_id)
    if identity.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User authentication required")
    async with uow:
        await TemporaryItemsResolutionService.delete_temporary_item(
            uow,
            temporary_item_id=temporary_item_id,
            resolved_by_user_id=identity.user_id,
            resolution_note="Удалён пользователем",
        )
        item = await uow.temporary_items.get_by_id(temporary_item_id)
    return build_temporary_item_response(item)
