from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device


class DevicesRepo:
    """Data access for devices table."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, device_id: UUID) -> Device | None:
        result = await self.session.execute(select(Device).where(Device.id == device_id))
        return result.scalar_one_or_none()

    async def get_by_site(self, site_id: UUID) -> list[Device]:
        result = await self.session.execute(select(Device).where(Device.site_id == site_id))
        return list(result.scalars().all())

    async def create(self, site_id: UUID, name: str | None = None) -> Device:
        device = Device(site_id=site_id, name=name, registration_token=uuid4())
        self.session.add(device)
        await self.session.flush()
        return device

    async def update_last_seen(self, device_id: UUID, ip: str | None = None, client_version: str | None = None) -> None:
        device = await self.get_by_id(device_id)
        if device is None:
            return

        device.last_seen_at = datetime.now(UTC)
        if ip is not None:
            device.last_ip = ip
        if client_version is not None:
            device.client_version = client_version

        await self.session.flush()
