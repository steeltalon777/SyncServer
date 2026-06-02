from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_uow, require_user_identity
from app.core.identity import Identity
from app.schemas.asset_register import IssuedAssetListResponse, IssuedAssetRow
from app.schemas.issue_object import (
    IssueObjectCreate,
    IssueObjectListResponse,
    IssueObjectMerge,
    IssueObjectResponse,
    IssueObjectUpdate,
)
from app.services.issue_objects_service import IssueObjectsService
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/issue-objects")

READ_ROLES = {"chief_storekeeper", "storekeeper", "observer"}
WRITE_ROLES = {"chief_storekeeper", "storekeeper"}


def _require_read(identity: Identity) -> None:
    if identity.has_global_business_access:
        return
    if identity.role not in READ_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="read issue_objects permission required")


def _require_write(identity: Identity) -> None:
    if identity.has_global_business_access:
        return
    if identity.role not in WRITE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="write issue_objects permission required")


def _require_merge(identity: Identity) -> None:
    if identity.has_global_business_access:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only chief_storekeeper or root may merge issue_objects")


@router.post("", response_model=IssueObjectResponse)
async def create_issue_object(
    payload: IssueObjectCreate,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> IssueObjectResponse:
    _require_write(identity)

    async with uow:
        issue_object = await uow.issue_objects.create_issue_object(
            display_name=payload.display_name,
            object_type=payload.object_type,
            code=payload.code,
        )

    return IssueObjectResponse.model_validate(issue_object)


@router.post("/merge", response_model=IssueObjectResponse)
async def merge_issue_objects(
    payload: IssueObjectMerge,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> IssueObjectResponse:
    _require_merge(identity)

    async with uow:
        try:
            merged = await uow.issue_objects.merge_issue_objects(
                source_id=payload.source_id,
                target_id=payload.target_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return IssueObjectResponse.model_validate(merged)


@router.get("/{issue_object_id}/assets", response_model=IssuedAssetListResponse)
async def list_issue_object_assets(
    issue_object_id: int,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    item_id: int | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> IssuedAssetListResponse:
    _require_read(identity)

    async with uow:
        rows, total_count = await uow.asset_registers.list_issued(
            issue_object_id=issue_object_id,
            item_id=item_id,
            search=search,
            page=page,
            page_size=page_size,
        )

    return IssuedAssetListResponse(
        items=[IssuedAssetRow.model_validate(row) for row in rows],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/{issue_object_id}", response_model=IssueObjectResponse)
async def get_issue_object(
    issue_object_id: int,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> IssueObjectResponse:
    _require_read(identity)
    service = IssueObjectsService()
    async with uow:
        issue_object = await service.get_issue_object(uow, issue_object_id)
    return IssueObjectResponse.model_validate(issue_object)


@router.patch("/{issue_object_id}", response_model=IssueObjectResponse)
async def update_issue_object(
    issue_object_id: int,
    payload: IssueObjectUpdate,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> IssueObjectResponse:
    _require_write(identity)
    service = IssueObjectsService()
    async with uow:
        issue_object = await service.update_issue_object(uow, issue_object_id, payload)
    return IssueObjectResponse.model_validate(issue_object)


@router.delete("/{issue_object_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_issue_object(
    issue_object_id: int,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> None:
    _require_write(identity)
    service = IssueObjectsService()
    async with uow:
        await service.delete_issue_object(uow, issue_object_id, identity.user_id)


@router.get("", response_model=IssueObjectListResponse)
async def list_issue_objects(
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    search: str | None = Query(None),
    object_type: str | None = Query(None),
    include_inactive: bool = False,
    include_deleted: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> IssueObjectListResponse:
    _require_read(identity)
    service = IssueObjectsService()
    async with uow:
        issue_objects, total_count = await service.list_issue_objects(
            uow,
            search=search,
            object_type=object_type,
            include_inactive=include_inactive,
            include_deleted=include_deleted,
            page=page,
            page_size=page_size,
        )

    return IssueObjectListResponse(
        items=[IssueObjectResponse.model_validate(row) for row in issue_objects],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )
