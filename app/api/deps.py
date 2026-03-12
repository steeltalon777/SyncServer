from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from time import monotonic
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.models.device import Device
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


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


async def require_device_auth(
    *,
    request: Request,
    uow: UnitOfWork,
    site_id: UUID,
    device_id: UUID,
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

    is_valid = (
        device.site_id == site_id
        and device.is_active
        and str(device.registration_token) == device_token
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )

    await uow.devices.update_last_seen(
        device_id=device_id,
        ip=get_client_ip(request),
        client_version=client_version,
    )
    return device


async def require_service_auth(
    *,
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    """Validate service token for trusted service authentication."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing authorization header",
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid authorization format, expected 'Bearer <token>'",
        )

    token = authorization[7:].strip()  # Remove "Bearer " prefix
    settings = get_settings()

    if not settings.SYNC_SERVER_SERVICE_TOKEN:
        logger.warning("SYNC_SERVER_SERVICE_TOKEN is not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="service authentication not configured",
        )

    if token != settings.SYNC_SERVER_SERVICE_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid service token",
        )


async def require_acting_user(
    *,
    request: Request,
    uow: UnitOfWork,
    x_acting_user_id: int = Header(alias="X-Acting-User-Id"),
    x_acting_site_id: UUID = Header(alias="X-Acting-Site-Id"),
) -> dict[str, int | UUID | str]:
    """Validate acting user context and check access permissions."""
    if not x_acting_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="missing acting user id",
        )

    if not x_acting_site_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="missing acting site id",
        )

    # Check if user has access to the site
    user_site_role = await uow.user_site_roles.get_by_user_and_site(
        user_id=x_acting_user_id,
        site_id=x_acting_site_id,
    )

    if not user_site_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user does not have access to this site",
        )

    return {
        "user_id": x_acting_user_id,
        "site_id": x_acting_site_id,
        "role": user_site_role.role,
    }


async def auth_catalog_headers(
    x_site_id: UUID = Header(alias="X-Site-Id"),
    x_device_id: UUID = Header(alias="X-Device-Id"),
    x_device_token: str | None = Header(default=None, alias="X-Device-Token"),
    x_client_version: str | None = Header(default=None, alias="X-Client-Version"),
) -> dict[str, UUID | str | None]:
    return {
        "site_id": x_site_id,
        "device_id": x_device_id,
        "device_token": x_device_token,
        "client_version": x_client_version,
    }


async def auth_service_headers(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_acting_user_id: int | None = Header(default=None, alias="X-Acting-User-Id"),
    x_acting_site_id: UUID | None = Header(default=None, alias="X-Acting-Site-Id"),
) -> dict[str, str | int | UUID | None]:
    """Collect service authentication headers."""
    return {
        "authorization": authorization,
        "acting_user_id": x_acting_user_id,
        "acting_site_id": x_acting_site_id,
    }


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


# Error response format
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
