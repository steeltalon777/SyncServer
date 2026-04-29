from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_uow, require_user_identity
from app.core.identity import Identity
from app.schemas.recipient import (
    RecipientCreate,
    RecipientListResponse,
    RecipientMerge,
    RecipientResponse,
    RecipientUpdate,
)
from app.services.recipients_service import RecipientsService
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/recipients")

WRITE_ROLES = {"chief_storekeeper", "storekeeper"}


def _require_read(identity: Identity) -> None:
    if identity.user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="read recipients permission required")


def _require_write(identity: Identity) -> None:
    if identity.has_global_business_access:
        return
    if identity.role not in WRITE_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="write recipients permission required")


def _require_merge(identity: Identity) -> None:
    if identity.has_global_business_access:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="only chief_storekeeper or root may merge recipients")


@router.post("", response_model=RecipientResponse)
async def create_recipient(
    payload: RecipientCreate,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> RecipientResponse:
    _require_write(identity)

    async with uow:
        recipient = await uow.recipients.create_recipient(
            display_name=payload.display_name,
            recipient_type=payload.recipient_type,
            personnel_no=payload.personnel_no,
        )

    return RecipientResponse.model_validate(recipient)


@router.post("/merge", response_model=RecipientResponse)
async def merge_recipients(
    payload: RecipientMerge,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> RecipientResponse:
    _require_merge(identity)

    async with uow:
        try:
            merged = await uow.recipients.merge_recipients(
                source_id=payload.source_id,
                target_id=payload.target_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return RecipientResponse.model_validate(merged)


@router.get("/{recipient_id}", response_model=RecipientResponse)
async def get_recipient(
    recipient_id: int,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> RecipientResponse:
    _require_read(identity)
    service = RecipientsService()
    async with uow:
        recipient = await service.get_recipient(uow, recipient_id)
    return RecipientResponse.model_validate(recipient)


@router.patch("/{recipient_id}", response_model=RecipientResponse)
async def update_recipient(
    recipient_id: int,
    payload: RecipientUpdate,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> RecipientResponse:
    _require_write(identity)
    service = RecipientsService()
    async with uow:
        recipient = await service.update_recipient(uow, recipient_id, payload)
    return RecipientResponse.model_validate(recipient)


@router.delete("/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipient(
    recipient_id: int,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> None:
    _require_write(identity)
    service = RecipientsService()
    async with uow:
        await service.delete_recipient(uow, recipient_id, identity.user_id)


@router.get("", response_model=RecipientListResponse)
async def list_recipients(
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    search: str | None = Query(None),
    recipient_type: str | None = Query(None),
    include_inactive: bool = False,
    include_deleted: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> RecipientListResponse:
    _require_read(identity)
    service = RecipientsService()
    async with uow:
        recipients, total_count = await service.list_recipients(
            uow,
            search=search,
            recipient_type=recipient_type,
            include_inactive=include_inactive,
            include_deleted=include_deleted,
            page=page,
            page_size=page_size,
        )

    return RecipientListResponse(
        items=[RecipientResponse.model_validate(row) for row in recipients],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )
