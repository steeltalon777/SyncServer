from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.admin_common import require_admin_basic
from app.api.deps import get_request_id, get_uow, require_user_identity
from app.core.identity import Identity
from app.schemas.audit import AuditEventListResponse, AuditEventResponse
from app.services.uow import UnitOfWork

router = APIRouter(prefix="/audit", tags=["admin-audit"])


@router.get("", response_model=AuditEventListResponse)
async def list_audit_events(
    event_type: str | None = Query(default=None, max_length=64),
    actor_user_id: UUID | None = Query(default=None),
    site_id: int | None = Query(default=None),
    entity_type: str | None = Query(default=None, max_length=64),
    entity_id: str | None = Query(default=None, max_length=256),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    request_id: str = Depends(get_request_id),
) -> AuditEventListResponse:
    """List audit events with optional filters. Requires root or chief_storekeeper."""
    async with uow:
        require_admin_basic(identity)

        items, total_count = await uow.audit_events.list_events(
            event_type=event_type,
            actor_user_id=actor_user_id,
            site_id=site_id,
            entity_type=entity_type,
            entity_id=entity_id,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )

    return AuditEventListResponse(
        items=[AuditEventResponse.model_validate(e) for e in items],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/{event_id}", response_model=AuditEventResponse)
async def get_audit_event(
    event_id: UUID,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> AuditEventResponse:
    """Get a single audit event by event_id. Requires root or chief_storekeeper."""
    async with uow:
        require_admin_basic(identity)
        event = await uow.audit_events.get_by_id(event_id)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="audit event not found",
            )
    return AuditEventResponse.model_validate(event)
