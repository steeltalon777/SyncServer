from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select

from app.models.device import Device
from app.services.uow import UnitOfWork


class AdminDevicesService:
    @staticmethod
    async def validate_device_code_unique(
        uow: UnitOfWork,
        *,
        device_code: str,
        current_device_id: int | None = None,
    ) -> None:
        existing = await uow.devices.get_by_code(device_code)
        if existing is not None and existing.id != current_device_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"device code '{device_code}' already exists",
            )

    @staticmethod
    async def get_device_required(uow: UnitOfWork, device_id: int) -> Device:
        device = await uow.devices.get_by_id(device_id)
        if not device:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="device not found")
        return device

    @staticmethod
    async def validate_site_exists(uow: UnitOfWork, site_id: int | None) -> None:
        if site_id is None:
            return
        site = await uow.sites.get_by_id(site_id)
        if not site:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="site not found")

    @staticmethod
    async def list_devices(
        uow: UnitOfWork,
        *,
        site_id: int | None,
        is_active: bool | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Device], int]:
        stmt = select(Device)
        if site_id is not None:
            stmt = stmt.where(Device.site_id == site_id)
        if is_active is not None:
            stmt = stmt.where(Device.is_active == is_active)
        if search:
            token = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Device.device_code.ilike(token),
                    Device.device_name.ilike(token),
                )
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = (await uow.session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(Device.id).offset((page - 1) * page_size).limit(page_size)
        devices = list((await uow.session.execute(stmt)).scalars().all())
        return devices, int(total_count)

    @staticmethod
    async def create_device(
        uow: UnitOfWork,
        *,
        device_code: str | None,
        device_name: str,
        site_id: int | None,
        is_active: bool,
    ) -> Device:
        await AdminDevicesService.validate_site_exists(uow, site_id)
        resolved_device_code = device_code or f"device-{uuid4().hex[:10]}"
        await AdminDevicesService.validate_device_code_unique(uow, device_code=resolved_device_code)

        device = Device(
            device_code=resolved_device_code,
            device_name=device_name,
            site_id=site_id,
            is_active=is_active,
            device_token=uuid4(),
        )
        uow.session.add(device)
        await uow.session.flush()
        await uow.session.refresh(device)
        return device

    @staticmethod
    async def update_device(
        uow: UnitOfWork,
        *,
        device_id: int,
        payload,
    ) -> Device:
        device = await AdminDevicesService.get_device_required(uow, device_id)

        if payload.site_id is not None:
            await AdminDevicesService.validate_site_exists(uow, payload.site_id)

        if payload.device_code is not None:
            await AdminDevicesService.validate_device_code_unique(
                uow,
                device_code=payload.device_code,
                current_device_id=device.id,
            )
            device.device_code = payload.device_code
        if payload.device_name is not None:
            device.device_name = payload.device_name
        if "site_id" in payload.model_fields_set:
            device.site_id = payload.site_id
        if payload.is_active is not None:
            device.is_active = payload.is_active

        await uow.session.flush()
        await uow.session.refresh(device)
        return device

    @staticmethod
    async def delete_device(uow: UnitOfWork, *, device_id: int) -> Device:
        device = await AdminDevicesService.get_device_required(uow, device_id)
        device.is_active = False
        await uow.session.flush()
        await uow.session.refresh(device)
        return device

    @staticmethod
    async def rotate_device_token(
        uow: UnitOfWork,
        *,
        device_id: int,
    ) -> tuple[Device, datetime]:
        device = await AdminDevicesService.get_device_required(uow, device_id)
        device.device_token = uuid4()
        await uow.session.flush()
        await uow.session.refresh(device)
        return device, datetime.now(UTC)
