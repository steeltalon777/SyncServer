from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime, timezone
from app.models.device import Device


class DeviceRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, device_id: UUID) -> Device | None:
        query = select(Device).where(Device.id == device_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_site(self, site_id: UUID) -> list[Device]:
        query = select(Device).where(Device.site_id == site_id)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def create(self, site_id: UUID, name: str = None) -> Device:
        import uuid
        device = Device(
            site_id=site_id,
            name=name,
            registration_token=uuid.uuid4(),
            is_active=True
        )
        self.db.add(device)
        await self.db.flush()
        return device

    async def update_last_seen(self, device_id: UUID, ip: str = None):
        device = await self.get_by_id(device_id)
        if device:
            device.last_seen_at = datetime.now(timezone.utc)
            if ip:
                device.last_ip = ip
            await self.db.flush()