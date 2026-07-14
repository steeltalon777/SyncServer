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
from app.schemas.issue_object_category import (
    IssueObjectCategoryCreate,
    IssueObjectCategoryListResponse,
    IssueObjectCategoryResponse,
    IssueObjectCategoryUpdate,
    TreeResponse,
)
from app.services.audit_helper import record_audit_event
from app.services.issue_objects_service import IssueObjectCategoriesService, IssueObjectsService
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/issue-objects")
router_categories = APIRouter(prefix="/issue-object-categories")

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


# ---------------------------------------------------------------------------
# Issue Object CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=IssueObjectResponse)
async def create_issue_object(
    payload: IssueObjectCreate,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> IssueObjectResponse:
    _require_write(identity)
    service = IssueObjectsService()
    async with uow:
        issue_object = await service.create_issue_object(uow, payload)
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

        # TZ-AUDIT_BACKEND_FOUNDATION §8.3 — issue_object.merge audit.
        event = await record_audit_event(
            uow,
            event_type="issue_object.merge",
            event_version=2,
            actor_user_id=identity.user_id,
            entity_type="issue_object",
            entity_id=str(payload.target_id),
            summary=f"Объект выдачи #{payload.source_id} слит с #{payload.target_id}",
            changes={
                "source_id": payload.source_id,
                "target_id": payload.target_id,
            },
            outcome="success",
        )
        await uow.audit_events.insert_resource(
            audit_event_id=int(event.id),
            resource_type="issue_object",
            resource_id=str(payload.source_id),
            relation="merge_source",
        )
        await uow.audit_events.insert_resource(
            audit_event_id=int(event.id),
            resource_type="issue_object",
            resource_id=str(payload.target_id),
            relation="merge_target",
        )

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


@router.get("/tree", response_model=list[TreeResponse])
async def get_issue_objects_tree(
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    search: str | None = Query(None),
    include_inactive: bool = False,
    include_deleted: bool = False,
) -> list[TreeResponse]:
    _require_read(identity)
    service = IssueObjectCategoriesService()
    async with uow:
        return await service.build_tree(
            uow,
            search=search,
            include_inactive=include_inactive,
            include_deleted=include_deleted,
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
    category_id: int | None = Query(None),
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
            category_id=category_id,
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


# ---------------------------------------------------------------------------
# IssueObjectCategory CRUD
# ---------------------------------------------------------------------------


@router_categories.post("", response_model=IssueObjectCategoryResponse)
async def create_category(
    payload: IssueObjectCategoryCreate,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> IssueObjectCategoryResponse:
    _require_write(identity)
    service = IssueObjectCategoriesService()
    async with uow:
        category = await service.create_category(
            uow,
            name=payload.name,
            parent_id=payload.parent_id,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
        )
    return IssueObjectCategoryResponse.model_validate(category)


@router_categories.get("", response_model=IssueObjectCategoryListResponse)
async def list_categories(
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    search: str | None = Query(None),
    parent_id: int | None = Query(None),
    is_active: bool | None = Query(None),
    include_deleted: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> IssueObjectCategoryListResponse:
    _require_read(identity)
    service = IssueObjectCategoriesService()
    async with uow:
        categories, total_count = await service.list_categories(
            uow,
            search=search,
            parent_id=parent_id,
            is_active=is_active,
            include_deleted=include_deleted,
            page=page,
            page_size=page_size,
        )
    return IssueObjectCategoryListResponse(
        items=[IssueObjectCategoryResponse.model_validate(c) for c in categories],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router_categories.get("/{category_id}", response_model=IssueObjectCategoryResponse)
async def get_category(
    category_id: int,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> IssueObjectCategoryResponse:
    _require_read(identity)
    service = IssueObjectCategoriesService()
    async with uow:
        category = await service.get_category(uow, category_id)
    return IssueObjectCategoryResponse.model_validate(category)


@router_categories.patch("/{category_id}", response_model=IssueObjectCategoryResponse)
async def update_category(
    category_id: int,
    payload: IssueObjectCategoryUpdate,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> IssueObjectCategoryResponse:
    _require_write(identity)
    service = IssueObjectCategoriesService()
    async with uow:
        category = await service.update_category(
            uow,
            category_id=category_id,
            name=payload.name,
            parent_id=payload.parent_id,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
            fields_set=payload.model_fields_set,
        )
    return IssueObjectCategoryResponse.model_validate(category)


@router_categories.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> None:
    _require_write(identity)
    service = IssueObjectCategoriesService()
    async with uow:
        await service.delete_category(uow, category_id, identity.user_id)
