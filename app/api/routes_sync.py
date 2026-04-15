from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import (
    enforce_rate_limit,
    get_request_id,
    get_uow,
    require_device_identity,
    require_user_identity,
)
from app.core.config import get_settings
from app.core.identity import Identity
from app.models.site import Site
from app.schemas.sync import (
    BootstrapData,
    BootstrapSyncRequest,
    BootstrapSyncResponse,
    PingRequest,
    PingResponse,
    PullEvent,
    PullRequest,
    PullResponse,
    PushRequest,
    PushResponse,
)
from app.services.sync_service import SyncService
from app.services.uow import UnitOfWork

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()


@router.post("/ping", response_model=PingResponse)
async def ping(
    payload: PingRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_device_identity),
    x_client_version: str | None = Header(default=None, alias="X-Client-Version"),
) -> PingResponse:
    await enforce_rate_limit(request=request, device_id=payload.device_id, route_name="ping")

    async with uow:
        server_seq_upto = await uow.events.get_max_server_seq(payload.site_id)

    logger.info(
        "request_id=%s ping site_id=%s device_id=%s outbox_count=%s",
        get_request_id(request),
        payload.site_id,
        payload.device_id,
        payload.outbox_count,
    )

    return PingResponse(
        server_time=datetime.now(UTC),
        server_seq_upto=server_seq_upto,
        backoff_seconds=0,
    )


@router.post("/push", response_model=PushResponse)
async def push(
    payload: PushRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_device_identity),
    x_client_version: str | None = Header(default=None, alias="X-Client-Version"),
) -> PushResponse:
    if len(payload.events) > settings.MAX_PUSH_EVENTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"events batch too large, max={settings.MAX_PUSH_EVENTS}",
        )

    await enforce_rate_limit(request=request, device_id=payload.device_id, route_name="push")

    service = SyncService()
    try:
        async with uow:
            response = await service.process_push(uow=uow, request=payload)
            site_max_seq = await uow.events.get_max_server_seq(payload.site_id)
            response.server_seq_upto = max(response.server_seq_upto, site_max_seq)
    except HTTPException:
        raise
    except Exception:
        logger.exception("request_id=%s unexpected push failure", get_request_id(request))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal server error")

    for rejected in response.rejected:
        if rejected.reason_code == "uuid_collision":
            logger.warning(
                "request_id=%s push uuid_collision event_uuid=%s batch_id=%s",
                get_request_id(request),
                rejected.event_uuid,
                payload.batch_id,
            )

    logger.info(
        "request_id=%s push site_id=%s device_id=%s batch_id=%s events=%s accepted=%s duplicates=%s rejected=%s",
        get_request_id(request),
        payload.site_id,
        payload.device_id,
        payload.batch_id,
        len(payload.events),
        len(response.accepted),
        len(response.duplicates),
        len(response.rejected),
    )
    return response


@router.post("/pull", response_model=PullResponse)
async def pull(
    payload: PullRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_device_identity),
    x_client_version: str | None = Header(default=None, alias="X-Client-Version"),
) -> PullResponse:
    limit = payload.limit if "limit" in payload.model_fields_set else settings.DEFAULT_PULL_LIMIT

    async with uow:
        pulled_events = await uow.events.pull(site_id=payload.site_id, since_seq=payload.since_seq, limit=limit)
        server_seq_upto = await uow.events.get_max_server_seq(payload.site_id)

    response_events = [
        PullEvent(
            event_uuid=event.event_uuid,
            server_seq=event.server_seq,
            event_type=event.event_type,
            event_datetime=event.event_datetime,
            schema_version=event.schema_version,
            payload=event.payload,
        )
        for event in pulled_events
    ]

    next_since_seq = payload.since_seq
    if response_events:
        next_since_seq = response_events[-1].server_seq

    logger.info(
        "request_id=%s pull site_id=%s device_id=%s since_seq=%s returned=%s",
        get_request_id(request),
        payload.site_id,
        payload.device_id,
        payload.since_seq,
        len(response_events),
    )

    return PullResponse(
        events=response_events,
        server_time=datetime.now(UTC),
        server_seq_upto=server_seq_upto,
        next_since_seq=next_since_seq,
    )


@router.post("/bootstrap/sync", response_model=BootstrapSyncResponse)
async def bootstrap_sync(
    payload: BootstrapSyncRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    x_client_version: str | None = Header(default=None, alias="X-Client-Version"),
) -> BootstrapSyncResponse:
    """Endpoint начальной загрузки для Django-клиента.

    Primary auth: X-User-Token (root). Device token — опционален для логов/привязки.
    site_id и device_id из body могут быть 0 — сервер определит устройство
    по токену и вернёт реальные координаты клиенту.
    """
    await enforce_rate_limit(request=request, device_id=payload.device_id or "unknown", route_name="bootstrap")

    if not identity.is_root:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="root permissions required for bootstrap",
        )

    async with uow:
        sites_result = await uow.session.execute(
            select(Site).where(Site.is_active.is_(True))
        )
        sites = sites_result.scalars().all()
        available_sites = [
            {
                "site_id": site.id,
                "code": site.code,
                "name": site.name,
                "is_active": site.is_active,
            }
            for site in sites
        ]

    root_user = identity.user
    root_user_payload = {
        "id": str(root_user.id),
        "username": root_user.username,
        "email": root_user.email,
        "full_name": root_user.full_name,
        "is_active": root_user.is_active,
        "is_root": root_user.is_root,
        "role": root_user.role,
    }

    return BootstrapSyncResponse(
        server_time=datetime.now(UTC),
        protocol_version="1.0",
        is_root=True,
        root_user=root_user_payload,
        root_role=root_user.role,
        device_id=identity.device_id,
        device_registered=identity.device is not None,
        message="bootstrap complete",
        bootstrap_data=BootstrapData(
            available_sites=available_sites,
            protocol_version="1.0",
            settings={
                "max_push_events": settings.MAX_PUSH_EVENTS,
                "default_pull_limit": settings.DEFAULT_PULL_LIMIT,
            },
        ),
    )
