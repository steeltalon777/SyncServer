from __future__ import annotations

import structlog
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_request_id, get_uow, require_user_identity
from app.core.identity import Identity
from app.services.corrections_service import CorrectionsService
from app.services.uow import UnitOfWork
from app.services.operations_policy import OperationsPolicy

router = APIRouter(prefix="/operations")
logger = structlog.get_logger()


def _require_root(identity: Identity):
    """All correction endpoints require root (TZ §1.1)."""
    if not identity.is_root:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="corrections require root permissions",
        )


@router.get("/{operation_id}/corrections/{correction_id}")
async def get_correction(
    operation_id: UUID,
    correction_id: UUID,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
):
    """Get a correction draft by ID."""
    _require_root(identity)
    async with uow:
        from app.services.corrections_service import CorrectionsService
        correction = await uow.corrections.get_correction_by_id(correction_id)
        if correction is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="correction not found")
        return CorrectionsService._correction_to_dict(correction)


@router.post("/{operation_id}/corrections")
async def begin_correction(
    operation_id: UUID,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
):
    """Begin a correction by cloning the current baseline into a draft.

    INV-C7: Клонирует все baseline lines (не пустой).
    INV-C19: Partial unique index — одна active draft на operation.
    """
    _require_root(identity)
    async with uow:
        result = await CorrectionsService.begin_correction(
            uow=uow,
            operation_id=operation_id,
            user_id=identity.user_id,
        )

    logger.info(
        "begin_correction",
        request_id=get_request_id(request),
        operation_id=str(operation_id),
        correction_id=result.get("id"),
        user=identity.user_id,
    )
    return result


@router.put("/{operation_id}/corrections/{correction_id}")
async def update_correction_put(
    operation_id: UUID,
    correction_id: UUID,
    body: dict,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
):
    """PUT full target state for a correction draft.

    INV-C9: PUT full target state. Отсутствие строки = REMOVED.
    """
    _require_root(identity)
    expected_version = body.get("expected_version")
    if expected_version is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="expected_version is required",
        )

    async with uow:
        result = await CorrectionsService.update_correction_put(
            uow=uow,
            correction_id=correction_id,
            expected_version=expected_version,
            lines=body.get("lines", []),
        )

    logger.info(
        "update_correction_put",
        request_id=get_request_id(request),
        correction_id=str(correction_id),
        user=identity.user_id,
    )
    return result


@router.post("/{operation_id}/corrections/{correction_id}/lines")
async def add_correction_line(
    operation_id: UUID,
    correction_id: UUID,
    body: dict,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
):
    """POST a new line to a correction draft."""
    _require_root(identity)
    expected_version = body.get("expected_version")
    if expected_version is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="expected_version is required",
        )

    async with uow:
        result = await CorrectionsService.add_correction_line(
            uow=uow,
            correction_id=correction_id,
            expected_version=expected_version,
            line_data=body,
        )

    return result


@router.patch("/{operation_id}/corrections/{correction_id}/lines/{line_uuid}")
async def update_correction_line(
    operation_id: UUID,
    correction_id: UUID,
    line_uuid: UUID,
    body: dict,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
):
    """PATCH a line in a correction draft."""
    _require_root(identity)
    expected_version = body.get("expected_version")
    if expected_version is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="expected_version is required",
        )

    async with uow:
        result = await CorrectionsService.update_correction_line(
            uow=uow,
            correction_id=correction_id,
            line_uuid=line_uuid,
            expected_version=expected_version,
            updates=body,
        )

    return result


@router.delete("/{operation_id}/corrections/{correction_id}/lines/{line_uuid}")
async def delete_correction_line(
    operation_id: UUID,
    correction_id: UUID,
    line_uuid: UUID,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
):
    """DELETE a line from a correction draft."""
    _require_root(identity)
    body = await request.json()
    expected_version = body.get("expected_version")
    if expected_version is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="expected_version is required",
        )

    async with uow:
        await CorrectionsService.delete_correction_line(
            uow=uow,
            correction_id=correction_id,
            line_uuid=line_uuid,
            expected_version=expected_version,
        )

    return {"status": "deleted"}


@router.post("/{operation_id}/corrections/{correction_id}/submit")
async def submit_correction(
    operation_id: UUID,
    correction_id: UUID,
    body: dict,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
):
    """Submit a correction: compute diff, validate, apply effects atomically."""
    _require_root(identity)
    expected_version = body.get("expected_version")
    if expected_version is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="expected_version is required",
        )

    async with uow:
        result = await CorrectionsService.submit_correction(
            uow=uow,
            correction_id=correction_id,
            user_id=identity.user_id,
            expected_version=expected_version,
            idempotency_key=body.get("idempotency_key"),
        )

    logger.info(
        "submit_correction",
        request_id=get_request_id(request),
        correction_id=str(correction_id),
        user=identity.user_id,
    )
    return result


@router.delete("/{operation_id}/corrections/{correction_id}")
async def abandon_correction(
    operation_id: UUID,
    correction_id: UUID,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
):
    """Abandon a correction draft."""
    _require_root(identity)
    body = await request.json()
    expected_version = body.get("expected_version")
    if expected_version is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="expected_version is required",
        )

    async with uow:
        result = await CorrectionsService.abandon_correction(
            uow=uow,
            correction_id=correction_id,
            expected_version=expected_version,
            user_id=identity.user_id,
        )

    logger.info(
        "abandon_correction",
        request_id=get_request_id(request),
        correction_id=str(correction_id),
        user=identity.user_id,
    )
    return result
