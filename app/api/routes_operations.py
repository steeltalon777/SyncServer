from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.api.deps import (
    get_request_id,
    get_uow,
    require_acting_user,
    require_service_auth,
)
from app.schemas.operation import (
    OperationCancel,
    OperationCreate,
    OperationFilter,
    OperationListResponse,
    OperationResponse,
    OperationSubmit,
    OperationUpdate,
)
from app.services.access_guard import AccessGuard
from app.services.access_service import AccessService
from app.services.operations_service import OperationsService
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/operations")
logger = logging.getLogger(__name__)


@router.get("", response_model=OperationListResponse)
async def list_operations(
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
    site_id: UUID | None = Query(None, description="Filter by site ID"),
    type: str | None = Query(None, description="Filter by operation type"),
    status: str | None = Query(None, description="Filter by operation status"),
    created_by_user_id: int | None = Query(None, description="Filter by creator user ID"),
    created_after: str | None = Query(None, description="Filter by creation date after"),
    created_before: str | None = Query(None, description="Filter by creation date before"),
    updated_after: str | None = Query(None, description="Filter by update date after"),
    updated_before: str | None = Query(None, description="Filter by update date before"),
    search: str | None = Query(None, description="Search in notes"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Page size"),
) -> OperationListResponse:
    """List operations with filtering."""
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )

        access_service = AccessService(uow)

        permissions = await access_service.get_user_permissions(
            user_context["user_id"],
            user_context["site_id"],
        )
        if not permissions["can_read_operations"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="read operations permission required",
            )

        user_accesses = await uow.user_site_roles.get_sites_for_user(user_context["user_id"])
        user_site_ids = [access.site_id for access in user_accesses]

        if site_id is not None and site_id not in user_site_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="user does not have access to requested site",
            )

        filter_data = OperationFilter(
            site_id=site_id,
            type=type,
            status=status,
            created_by_user_id=created_by_user_id,
            created_after=created_after,
            created_before=created_before,
            updated_after=updated_after,
            updated_before=updated_before,
            search=search,
        )

        operations, total_count = await uow.operations.list_operations(
            filter=filter_data,
            user_site_ids=user_site_ids,
            page=page,
            page_size=page_size,
        )

    operation_responses = [OperationResponse.model_validate(op) for op in operations]

    logger.info(
        "request_id=%s list_operations user_id=%s site_id=%s returned=%s total=%s",
        get_request_id(request),
        user_context["user_id"],
        user_context["site_id"],
        len(operation_responses),
        total_count,
    )

    return OperationListResponse(
        items=operation_responses,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/{operation_id}", response_model=OperationResponse)
async def get_operation(
    operation_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> OperationResponse:
    """Get operation by ID."""
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )

        access_service = AccessService(uow)

        permissions = await access_service.get_user_permissions(
            user_context["user_id"],
            user_context["site_id"],
        )
        if not permissions["can_read_operations"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="read operations permission required",
            )

        operation = await uow.operations.get_operation_by_id(operation_id)
        if not operation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Operation not found",
            )

        has_access = await access_service.can_read_site(
            user_context["user_id"],
            operation.site_id,
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have access to this operation",
            )

    logger.info(
        "request_id=%s get_operation operation_id=%s user_id=%s",
        get_request_id(request),
        operation_id,
        user_context["user_id"],
    )

    return OperationResponse.model_validate(operation)


@router.post("", response_model=OperationResponse)
async def create_operation(
    operation_data: OperationCreate,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> OperationResponse:
    """Create a new operation."""
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )

        access_service = AccessService(uow)

        await AccessGuard.require_storekeeper(
            access_service,
            user_context["user_id"],
            operation_data.site_id,
        )

        result = await OperationsService.create_operation(
            uow=uow,
            operation_data=operation_data,
            user_id=user_context["user_id"],
        )

    logger.info(
        "request_id=%s create_operation operation_uuid=%s type=%s user_id=%s site_id=%s lines=%s",
        get_request_id(request),
        result["operation_uuid"],
        operation_data.type,
        user_context["user_id"],
        operation_data.site_id,
        len(operation_data.lines),
    )

    return OperationResponse.model_validate(result["operation"])


@router.patch("/{operation_id}", response_model=OperationResponse)
async def update_operation(
    operation_id: int,
    update_data: OperationUpdate,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> OperationResponse:
    """Update an operation (draft only)."""
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )

        access_service = AccessService(uow)

        operation = await uow.operations.get_operation_by_id(operation_id)
        if not operation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Operation not found",
            )

        await AccessGuard.require_storekeeper(
            access_service,
            user_context["user_id"],
            operation.site_id,
        )

        if operation.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot update operation with status {operation.status}",
            )

        if update_data.notes is not None:
            operation.notes = update_data.notes

        if update_data.lines is not None:
            await uow.operations.delete_operation_lines(operation_id)

            for line_data in update_data.lines:
                await uow.operations.create_operation_line(
                    operation_id=operation_id,
                    line_number=line_data.line_number,
                    item_id=line_data.item_id,
                    quantity=line_data.quantity,
                    source_site_id=line_data.source_site_id,
                    target_site_id=line_data.target_site_id,
                    notes=line_data.notes,
                )

        updated_operation = await uow.operations.get_operation_by_id(operation_id)

    logger.info(
        "request_id=%s update_operation operation_id=%s user_id=%s",
        get_request_id(request),
        operation_id,
        user_context["user_id"],
    )

    return OperationResponse.model_validate(updated_operation)


@router.post("/{operation_id}/submit", response_model=OperationResponse)
async def submit_operation(
    operation_id: int,
    submit_data: OperationSubmit,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> OperationResponse:
    """Submit an operation."""
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )

        access_service = AccessService(uow)

        operation = await uow.operations.get_operation_by_id(operation_id)
        if not operation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Operation not found",
            )

        await AccessGuard.require_storekeeper(
            access_service,
            user_context["user_id"],
            operation.site_id,
        )

        result = await OperationsService.submit_operation(
            uow=uow,
            operation_id=operation_id,
            user_id=user_context["user_id"],
        )

    logger.info(
        "request_id=%s submit_operation operation_id=%s user_id=%s",
        get_request_id(request),
        operation_id,
        user_context["user_id"],
    )

    return OperationResponse.model_validate(result["operation"])


@router.post("/{operation_id}/cancel", response_model=OperationResponse)
async def cancel_operation(
    operation_id: int,
    cancel_data: OperationCancel,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> OperationResponse:
    """Cancel an operation."""
    await require_service_auth(request=request, authorization=authorization)

    async with uow:
        user_context = await require_acting_user(
            request=request,
            uow=uow,
            x_acting_user_id=x_acting_user_id,
            x_acting_site_id=x_acting_site_id,
        )

        access_service = AccessService(uow)

        operation = await uow.operations.get_operation_by_id(operation_id)
        if not operation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Operation not found",
            )

        await AccessGuard.require_storekeeper(
            access_service,
            user_context["user_id"],
            operation.site_id,
        )

        result = await OperationsService.cancel_operation(
            uow=uow,
            operation_id=operation_id,
            user_id=user_context["user_id"],
            reason=cancel_data.reason,
        )

    logger.info(
        "request_id=%s cancel_operation operation_id=%s user_id=%s reason=%s",
        get_request_id(request),
        operation_id,
        user_context["user_id"],
        cancel_data.reason,
    )

    return OperationResponse.model_validate(result["operation"])