from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from time import monotonic
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.identity import Identity
from app.models.device import Device
from app.services.identity_service import IdentityService
from app.services.uow import UnitOfWork

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._last_hit: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str, min_interval_seconds: float) -> None:
        now = monotonic()
        async with self._lock:
            previous = self._last_hit.get(key)
            if previous is not None and now - previous < min_interval_seconds:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="rate limit exceeded",
                )
            self._last_hit[key] = now


rate_limiter = InMemoryRateLimiter()


async def get_uow(db: AsyncSession = Depends(get_db)) -> AsyncGenerator[UnitOfWork, None]:
    yield UnitOfWork(db)


async def get_identity_service(
    uow: UnitOfWork = Depends(get_uow),
) -> IdentityService:
    return IdentityService(uow)


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


async def require_user_token_auth(
    request: Request,
    identity_service: IdentityService = Depends(get_identity_service),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
) -> Identity:
    if not x_user_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing X-User-Token",
        )
    return await identity_service.resolve_user_by_token(x_user_token)


async def require_device_token_auth(
    request: Request,
    identity_service: IdentityService = Depends(get_identity_service),
    x_device_token: UUID | None = Header(default=None, alias="X-Device-Token"),
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
    x_client_version: str | None = Header(default=None, alias="X-Client-Version"),
) -> Identity:
    if not x_device_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing X-Device-Token",
        )
    return await identity_service.resolve_current_identity(
        device_id=x_device_id,
        device_token=x_device_token,
        client_ip=get_client_ip(request),
        client_version=x_client_version,
    )


async def require_token_auth(
    request: Request,
    identity_service: IdentityService = Depends(get_identity_service),
    x_user_token: UUID | None = Header(default=None, alias="X-User-Token"),
    x_device_token: UUID | None = Header(default=None, alias="X-Device-Token"),
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
    x_client_version: str | None = Header(default=None, alias="X-Client-Version"),
) -> Identity:
    return await identity_service.resolve_current_identity(
        user_token=x_user_token,
        device_id=x_device_id,
        device_token=x_device_token,
        client_ip=get_client_ip(request),
        client_version=x_client_version,
    )


async def require_device_auth(
    *,
    request: Request,
    uow: UnitOfWork,
    site_id: UUID | int | str,
    device_id: UUID | int | str,
    device_token: str | None,
    client_version: str | None,
) -> Device:
    if not device_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )

    device = await uow.devices.get_by_id(device_id)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )

    token_value = getattr(device, "device_token", None) or getattr(device, "registration_token", None)
    is_valid = (
        str(device.site_id) == str(site_id)
        and device.is_active
        and str(token_value) == str(device_token)
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )

    await uow.devices.update_last_seen(
        device_id=device.id,
        ip=get_client_ip(request),
        client_version=client_version,
    )
    return device


async def enforce_rate_limit(request: Request, device_id: UUID, route_name: str) -> None:
    ip = get_client_ip(request)

    if route_name == "ping":
        key = f"{route_name}:{ip}:{device_id}"
        await rate_limiter.check(key=key, min_interval_seconds=5.0)
        return

    if route_name == "push":
        key = f"{route_name}:{ip}:{device_id}"
        await rate_limiter.check(key=key, min_interval_seconds=1.0)
        return

    logger.debug("No rate limit configured for route=%s", route_name)


def error_response(
    status_code: int,
    message: str,
    details: dict | None = None,
    error_code: str | None = None,
) -> JSONResponse:
    """Standard error response format."""
    error_body = {
        "error": {
            "code": error_code or f"HTTP_{status_code}",
            "message": message,
        }
    }
    if details:
        error_body["error"]["details"] = details
    return JSONResponse(
        status_code=status_code,
        content=error_body,
    )
