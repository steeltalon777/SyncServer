from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.admin_common import require_admin_basic
from app.api.deps import get_uow, require_user_identity
from app.core.identity import Identity
from app.schemas.admin import (
    DeviceCreate,
    DeviceListResponse,
    DeviceResponse,
    DeviceTokenResponse,
    DeviceWithTokenResponse,
    DeviceUpdate,
)
from app.services.admin_devices_service import AdminDevicesService
from app.services.uow import UnitOfWork

router = APIRouter(tags=["admin"])


@router.get("/devices/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: int,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> DeviceResponse:
    async with uow:
        require_admin_basic(identity)
        device = await AdminDevicesService.get_device_required(uow, device_id)
    return DeviceResponse.model_validate(device)


@router.get("/devices", response_model=DeviceListResponse)
async def list_devices(
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
    site_id: int | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> DeviceListResponse:
    async with uow:
        require_admin_basic(identity)
        devices, total_count = await AdminDevicesService.list_devices(
            uow,
            site_id=site_id,
            is_active=is_active,
            search=search,
            page=page,
            page_size=page_size,
        )

    return DeviceListResponse(
        devices=[DeviceResponse.model_validate(device) for device in devices],
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


@router.post("/devices", response_model=DeviceWithTokenResponse)
async def create_device(
    payload: DeviceCreate,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> DeviceWithTokenResponse:
    async with uow:
        require_admin_basic(identity)
        device = await AdminDevicesService.create_device(
            uow,
            device_code=payload.device_code,
            device_name=payload.device_name,
            site_id=payload.site_id,
            is_active=payload.is_active,
        )
    return DeviceWithTokenResponse.model_validate(device)


@router.patch("/devices/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: int,
    payload: DeviceUpdate,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> DeviceResponse:
    async with uow:
        require_admin_basic(identity)
        device = await AdminDevicesService.update_device(
            uow,
            device_id=device_id,
            payload=payload,
        )
    return DeviceResponse.model_validate(device)


@router.delete("/devices/{device_id}", response_model=DeviceResponse)
async def delete_device(
    device_id: int,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> DeviceResponse:
    async with uow:
        require_admin_basic(identity)
        device = await AdminDevicesService.delete_device(uow, device_id=device_id)
    return DeviceResponse.model_validate(device)


@router.post("/devices/{device_id}/rotate-token", response_model=DeviceTokenResponse)
async def rotate_device_token(
    device_id: int,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> DeviceTokenResponse:
    async with uow:
        require_admin_basic(identity)
        device, generated_at = await AdminDevicesService.rotate_device_token(uow, device_id=device_id)

        return DeviceTokenResponse(
            device_id=device.id,
            device_code=device.device_code,
            device_token=device.device_token,
            generated_at=generated_at,
        )
