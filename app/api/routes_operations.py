from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import get_request_id, get_uow, require_user_token_auth
from app.core.identity import Identity
from app.schemas.admin import SiteFilter
from app.schemas.operation import (
    OperationCancel,
    OperationCreate,
    OperationEffectiveAtUpdate,
    OperationFilter,
    OperationListResponse,
    OperationResponse,
    OperationStatus,
    OperationSubmit,
    OperationType,
    OperationUpdate,
)
from app.services.operations_service import OperationsService
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/operations")
logger = logging.getLogger(__name__)

READ_ROLES = {"chief_storekeeper", "storekeeper", "observer"}
WRITE_ROLES = {"chief_storekeeper", "storekeeper"}


def _require_read_site(identity: Identity, site_id: int) -> None:
    if identity.has_global_business_access:
        return
    if identity.role not in READ_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="read operations permission required")
    if not identity.has_site_access(site_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user has no view access to site")


def _require_operate_site(identity: Identity, site_id: int) -> None:
    if identity.has_global_business_access:
        return
    if identity.role not in WRITE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="operate permission required")
    if not identity.can_operate_at_site(site_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user has no operate access to site")


def _validate_move_access(identity: Identity, source_site_id: int | None, destination_site_id: int | None) -> None:
    if source_site_id is None or destination_site_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="MOVE operation requires source_site_id and destination_site_id",
        )
    _require_operate_site(identity, source_site_id)
    _require_operate_site(identity, destination_site_id)


def _require_operation_owner_or_supervisor(identity: Identity, operation) -> None:
    if identity.has_global_business_access:
        return
    if operation.created_by_user_id != identity.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only the operation creator, chief_storekeeper, or root may modify this draft",
        )


def _require_operation_submit_permission(identity: Identity) -> None:
    if identity.has_global_business_access:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="only chief_storekeeper or root may submit operations",
    )


def _require_operation_cancel_permission(identity: Identity, operation) -> None:
    if identity.has_global_business_access:
        return
    if operation.status == "draft" and operation.created_by_user_id == identity.user_id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="only chief_storekeeper or root may cancel submitted or other users operations",
    )


def _require_operation_effective_at_permission(identity: Identity) -> None:
    if identity.has_global_business_access:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="only chief_storekeeper or root may change operation effective_at",
    )


async def _resolve_readable_site_ids(uow: UnitOfWork, identity: Identity) -> list[int]:
    if identity.has_global_business_access:
        sites, _ = await uow.sites.list_sites(
            filter=SiteFilter(is_active=None),
            user_site_ids=None,
            page=1,
            page_size=1000,
        )
        return [site.id for site in sites]
    if identity.role not in READ_ROLES:
        return []
    return identity.get_accessible_site_ids()


@router.get("", response_model=OperationListResponse)
async def list_operations(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_token_auth),
    site_id: int | None = Query(None),
    operation_type: OperationType | None = Query(None, alias="type"),
    status_filter: OperationStatus | None = Query(None, alias="status"),
    created_by_user_id: UUID | None = Query(None),
    effective_after: datetime | None = Query(None),
    effective_before: datetime | None = Query(None),
    created_after: datetime | None = Query(None),
    created_before: datetime | None = Query(None),
    updated_after: datetime | None = Query(None),
    updated_before: datetime | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> OperationListResponse:
    async with uow:
        readable_site_ids = await _resolve_readable_site_ids(uow, identity)
        if not readable_site_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="read operations permission required")
        if site_id is not None:
            _require_read_site(identity, site_id)

        filter_data = OperationFilter(
            site_id=site_id,
            operation_type=operation_type,
            status=status_filter,
            created_by_user_id=created_by_user_id,
            effective_after=effective_after,
            effective_before=effective_before,
            created_after=created_after,
            created_before=created_before,
            updated_after=updated_after,
            updated_before=updated_before,
            search=search,
        )
        operations, total_count = await uow.operations.list_operations(
            filter=filter_data,
            user_site_ids=readable_site_ids,
            page=page,
            page_size=page_size,
        )

    return OperationListResponse(
        items=[OperationResponse.model_validate(op) for op in operations],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/{operation_id}", response_model=OperationResponse)
async def get_operation(
    operation_id: UUID,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_token_auth),
) -> OperationResponse:
    async with uow:
        operation = await uow.operations.get_operation_by_id(operation_id)
        if not operation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="operation not found")
        _require_read_site(identity, operation.site_id)

    logger.info("request_id=%s get_operation id=%s user=%s", get_request_id(request), operation_id, identity.user_id)
    return OperationResponse.model_validate(operation)


@router.post("", response_model=OperationResponse)
async def create_operation(
    operation_data: OperationCreate,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_token_auth),
) -> OperationResponse:
    _require_operate_site(identity, operation_data.site_id)
    if operation_data.operation_type == "MOVE":
        _validate_move_access(identity, operation_data.source_site_id, operation_data.destination_site_id)

    async with uow:
        result = await OperationsService.create_operation(
            uow=uow,
            operation_data=operation_data,
            user_id=identity.user_id,
        )

    operation = result["operation"]
    logger.info("request_id=%s create_operation id=%s user=%s", get_request_id(request), operation.id, identity.user_id)
    return OperationResponse.model_validate(operation)


@router.patch("/{operation_id}", response_model=OperationResponse)
async def update_operation(
    operation_id: UUID,
    update_data: OperationUpdate,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_token_auth),
) -> OperationResponse:
    if "effective_at" in update_data.model_fields_set:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="effective_at must be changed via PATCH /operations/{operation_id}/effective-at",
        )

    async with uow:
        operation = await uow.operations.get_operation_by_id(operation_id)
        if not operation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="operation not found")

        _require_operate_site(identity, operation.site_id)
        _require_operation_owner_or_supervisor(identity, operation)
        if operation.operation_type == "MOVE":
            source_site_id = update_data.source_site_id if "source_site_id" in update_data.model_fields_set else operation.source_site_id
            destination_site_id = (
                update_data.destination_site_id
                if "destination_site_id" in update_data.model_fields_set
                else operation.destination_site_id
            )
            _validate_move_access(identity, source_site_id, destination_site_id)

        updated_operation = await OperationsService.update_operation(
            uow=uow,
            operation_id=operation_id,
            update_data=update_data,
        )

    logger.info("request_id=%s update_operation id=%s user=%s", get_request_id(request), operation_id, identity.user_id)
    return OperationResponse.model_validate(updated_operation)


@router.patch("/{operation_id}/effective-at", response_model=OperationResponse)
async def update_operation_effective_at(
    operation_id: UUID,
    payload: OperationEffectiveAtUpdate,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_token_auth),
) -> OperationResponse:
    async with uow:
        operation = await uow.operations.get_operation_by_id(operation_id)
        if not operation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="operation not found")

        _require_read_site(identity, operation.site_id)
        _require_operation_effective_at_permission(identity)

        updated_operation = await OperationsService.update_operation_effective_at(
            uow=uow,
            operation_id=operation_id,
            effective_at=payload.effective_at,
        )

    logger.info(
        "request_id=%s update_operation_effective_at id=%s user=%s",
        get_request_id(request),
        operation_id,
        identity.user_id,
    )
    return OperationResponse.model_validate(updated_operation)


@router.post("/{operation_id}/submit", response_model=OperationResponse)
async def submit_operation(
    operation_id: UUID,
    submit_data: OperationSubmit,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_token_auth),
) -> OperationResponse:
    if not submit_data.submit:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="submit must be true")

    async with uow:
        operation = await uow.operations.get_operation_by_id(operation_id)
        if not operation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="operation not found")

        _require_operate_site(identity, operation.site_id)
        _require_operation_submit_permission(identity)
        if operation.operation_type == "MOVE":
            _validate_move_access(identity, operation.source_site_id, operation.destination_site_id)

        result = await OperationsService.submit_operation(
            uow=uow,
            operation_id=operation_id,
            user_id=identity.user_id,
        )

    return OperationResponse.model_validate(result["operation"])


@router.post("/{operation_id}/cancel", response_model=OperationResponse)
async def cancel_operation(
    operation_id: UUID,
    cancel_data: OperationCancel,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_token_auth),
) -> OperationResponse:
    if not cancel_data.cancel:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="cancel must be true")

    async with uow:
        operation = await uow.operations.get_operation_by_id(operation_id)
        if not operation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="operation not found")

        _require_operate_site(identity, operation.site_id)
        _require_operation_cancel_permission(identity, operation)
        if operation.operation_type == "MOVE":
            _validate_move_access(identity, operation.source_site_id, operation.destination_site_id)

        result = await OperationsService.cancel_operation(
            uow=uow,
            operation_id=operation_id,
            user_id=identity.user_id,
            reason=cancel_data.reason,
        )

    logger.info("request_id=%s cancel_operation id=%s user=%s", get_request_id(request), operation_id, identity.user_id)
    return OperationResponse.model_validate(result["operation"])
