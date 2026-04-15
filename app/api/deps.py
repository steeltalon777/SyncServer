from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from time import monotonic

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.identity import Identity
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


async def enforce_rate_limit(request: Request, device_id: int | str, route_name: str) -> None:
    ip = get_client_ip(request)

    if route_name == "ping":
        key = f"{route_name}:{ip}:{device_id}"
        await rate_limiter.check(key=key, min_interval_seconds=5.0)
        return

    if route_name == "push":
        key = f"{route_name}:{ip}:{device_id}"
        await rate_limiter.check(key=key, min_interval_seconds=1.0)
        return

    if route_name == "bootstrap":
        key = f"{route_name}:{ip}:{device_id}"
        await rate_limiter.check(key=key, min_interval_seconds=10.0)
        return

    logger.debug("No rate limit configured for route=%s", route_name)


# ---------------------------------------------------------------------------
# Unified auth dependencies
# ---------------------------------------------------------------------------

async def require_identity(
    identity_service: IdentityService = Depends(get_identity_service),
    x_user_token: str | None = Header(default=None, alias="X-User-Token"),
    x_device_token: str | None = Header(default=None, alias="X-Device-Token"),
    x_client_version: str | None = Header(default=None, alias="X-Client-Version"),
    request: Request = None,  # injected by FastAPI automatically
) -> Identity:
    """
    Require at least one valid token (user or device).
    """
    return await identity_service.resolve_identity(
        user_token=x_user_token,
        device_token=x_device_token,
        client_ip=get_client_ip(request) if request else None,
        client_version=x_client_version,
    )


async def require_user_identity(
    identity_service: IdentityService = Depends(get_identity_service),
    x_user_token: str | None = Header(default=None, alias="X-User-Token"),
    x_device_token: str | None = Header(default=None, alias="X-Device-Token"),
    x_client_version: str | None = Header(default=None, alias="X-Client-Version"),
    request: Request = None,
) -> Identity:
    """
    Require valid X-User-Token. X-Device-Token is optional for audit context.
    """
    return await identity_service.resolve_identity(
        user_token=x_user_token,
        device_token=x_device_token,
        require_user=True,
        client_ip=get_client_ip(request) if request else None,
        client_version=x_client_version,
    )


async def require_device_identity(
    identity_service: IdentityService = Depends(get_identity_service),
    x_device_token: str | None = Header(default=None, alias="X-Device-Token"),
    x_user_token: str | None = Header(default=None, alias="X-User-Token"),
    x_client_version: str | None = Header(default=None, alias="X-Client-Version"),
    request: Request = None,
) -> Identity:
    """
    Require valid X-Device-Token. X-User-Token is optional.
    """
    return await identity_service.resolve_identity(
        user_token=x_user_token,
        device_token=x_device_token,
        require_device=True,
        client_ip=get_client_ip(request) if request else None,
        client_version=x_client_version,
    )


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
