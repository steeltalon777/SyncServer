from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device


class DevicesRepo:
    """Data access for devices table."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, device_id: int | UUID | str) -> Device | None:
        # Compatibility: tolerate string id in legacy flows.
        if isinstance(device_id, str) and device_id.isdigit():
            device_id = int(device_id)
        result = await self.session.execute(select(Device).where(Device.id == device_id))
        return result.scalar_one_or_none()

    async def get_by_site(self, site_id: int | UUID | str) -> list[Device]:
        if isinstance(site_id, str) and site_id.isdigit():
            site_id = int(site_id)
        result = await self.session.execute(select(Device).where(Device.site_id == site_id))
        return list(result.scalars().all())

    async def get_by_device_token(self, device_token: UUID) -> Device | None:
        result = await self.session.execute(
            select(Device).where(Device.device_token == device_token)
        )
        return result.scalar_one_or_none()

    async def create(self, site_id: int | None, name: str | None = None) -> Device:
        # Legacy compatibility: "name" maps to current "device_name".
        device = Device(
            site_id=site_id,
            device_name=name or "Unnamed Device",
            device_code=f"device-{uuid4().hex[:12]}",
            device_token=uuid4(),
            is_active=True,
        )
        self.session.add(device)
        await self.session.flush()
        return device

    async def update_last_seen(
        self,
        device_id: int | UUID | str,
        ip: str | None = None,
        client_version: str | None = None,
    ) -> None:
        device = await self.get_by_id(device_id)
        if device is None:
            return

        device.last_seen_at = datetime.now(UTC)
        await self.session.flush()
