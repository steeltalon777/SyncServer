from __future__ import annotations

import structlog
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import (
    enforce_rate_limit,
    get_request_id,
    get_uow,
    require_device_identity,
    require_identity,
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
    SyncStatusResponse,
)
from app.services.sync_service import SyncService
from app.services.uow import UnitOfWork

router = APIRouter()
logger = structlog.get_logger()
settings = get_settings()


@router.post("/ping", response_model=PingResponse)
async def ping(
    payload: PingRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_device_identity),
) -> PingResponse:
    await enforce_rate_limit(request=request, device_id=payload.device_id, route_name="ping")

    # sync_state is keyed by the authenticated device, not by the payload's
    # placeholder device_id. If the caller is a real device (token-based)
    # use identity.device_id; otherwise fall back to payload.device_id.
    sync_device_id = identity.device_id or payload.device_id

    async with uow:
        server_seq_upto = await uow.events.get_max_server_seq(payload.site_id)
        if sync_device_id and sync_device_id > 0:
            # Update per-device sync_state (ADR-0016).
            await uow.sync_state.upsert(
                device_id=sync_device_id,
                last_sequence_number=max(
                    server_seq_upto,
                    payload.last_server_seq or 0,
                ),
                status="online",
                last_error=None,
            )

    logger.info(
        "ping",
        request_id=get_request_id(request),
        site_id=payload.site_id,
        device_id=payload.device_id,
        outbox_count=payload.outbox_count,
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
) -> PushResponse:
    if len(payload.events) > settings.MAX_PUSH_EVENTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"events batch too large, max={settings.MAX_PUSH_EVENTS}",
        )

    await enforce_rate_limit(request=request, device_id=payload.device_id, route_name="push")

    service = SyncService()
    sync_device_id = identity.device_id or payload.device_id
    try:
        async with uow:
            result = await service.process_push(uow=uow, request=payload)
            site_max_seq = await uow.events.get_max_server_seq(payload.site_id)
            result.server_seq_upto = max(result.server_seq_upto, site_max_seq)

            if sync_device_id and sync_device_id > 0:
                # Update per-device sync_state (ADR-0016).
                # - last_sync_at = now() (always touch on any push activity)
                # - status = "online" if any accepted/duplicate, "error" if conflicts
                summary = result.summary or {}
                conflict_count = summary.get("conflict_count", 0)
                push_status = "online" if conflict_count == 0 else "error"
                await uow.sync_state.upsert(
                    device_id=sync_device_id,
                    last_sequence_number=max(
                        summary.get("max_server_seq", 0),
                        site_max_seq,
                    ),
                    status=push_status,
                    last_error=summary.get("last_error"),
                )
    except HTTPException:
        raise
    except Exception:
        logger.error("unexpected_push_failure", request_id=get_request_id(request), exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal server error")

    for rejected in result.rejected:
        if rejected.reason_code == "uuid_collision":
            logger.warning(
                "push_uuid_collision",
                request_id=get_request_id(request),
                event_uuid=rejected.event_uuid,
                batch_id=payload.batch_id,
            )

    logger.info(
        "push",
        request_id=get_request_id(request),
        site_id=payload.site_id,
        device_id=payload.device_id,
        batch_id=payload.batch_id,
        events=len(payload.events),
        accepted=len(result.accepted),
        duplicates=len(result.duplicates),
        rejected=len(result.rejected),
    )
    return result


@router.post("/pull", response_model=PullResponse)
async def pull(
    payload: PullRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_device_identity),
) -> PullResponse:
    limit = payload.limit if "limit" in payload.model_fields_set else settings.DEFAULT_PULL_LIMIT
    sync_device_id = identity.device_id or payload.device_id

    async with uow:
        pulled_events = await uow.events.pull(
            site_id=payload.site_id, since_seq=payload.since_seq, limit=limit
        )
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

        if sync_device_id and sync_device_id > 0:
            # Update per-device sync_state (ADR-0016).
            # last_sequence_number tracks the highest server_seq the device
            # has received, not the site's max. So we use next_since_seq
            # (the cursor the client should use next time).
            await uow.sync_state.upsert(
                device_id=sync_device_id,
                last_sequence_number=next_since_seq,
                status="online",
                last_error=None,
            )

    logger.info(
        "pull",
        request_id=get_request_id(request),
        site_id=payload.site_id,
        device_id=payload.device_id,
        since_seq=payload.since_seq,
        returned=len(response_events),
    )

    return PullResponse(
        events=response_events,
        server_time=datetime.now(UTC),
        server_seq_upto=server_seq_upto,
        next_since_seq=next_since_seq,
    )


@router.get("/sync/status/{device_id}", response_model=SyncStatusResponse)
async def get_sync_status(
    device_id: int,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_identity),
) -> SyncStatusResponse:
    """Per-device sync state snapshot (ADR-0016).

    Authorization:
    - Device token for the same device_id → 200
    - Device token for a different device_id → 403
    - Root user token → 200 for any device
    - Anonymous → 401 (handled by require_identity)
    """
    # Authorization: own device or root
    if identity.device is None and not identity.is_root:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="device or root token required",
        )

    if identity.device is not None and identity.device.id != device_id and not identity.is_root:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="cannot view sync state of another device",
        )

    async with uow:
        state = await uow.sync_state.get_by_device_id(device_id)
        # server_seq_upto is site-scoped. Use the requesting device's site_id
        # when available; otherwise look up the target device.
        device_site_id: int | None = None
        if identity.device is not None and identity.device.id == device_id:
            device_site_id = identity.device.site_id
        if device_site_id is None:
            target_device = await uow.devices.get_by_id(device_id)
            device_site_id = target_device.site_id if target_device else None
        server_seq_upto = (
            await uow.events.get_max_server_seq(device_site_id)
            if device_site_id is not None
            else 0
        )

    if state is None:
        # No sync_state record yet — return zeroed snapshot.
        return SyncStatusResponse(
            device_id=device_id,
            last_sequence_number=0,
            last_sync_at=None,
            status="unknown",
            server_seq_upto=server_seq_upto,
            behind_by=server_seq_upto,
        )

    behind_by = max(0, server_seq_upto - state.last_sequence_number)
    return SyncStatusResponse(
        device_id=device_id,
        last_sequence_number=state.last_sequence_number,
        last_sync_at=state.last_sync_at,
        status=state.status,
        server_seq_upto=server_seq_upto,
        behind_by=behind_by,
    )


@router.post("/bootstrap/sync", response_model=BootstrapSyncResponse)
async def bootstrap_sync(
    payload: BootstrapSyncRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
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
