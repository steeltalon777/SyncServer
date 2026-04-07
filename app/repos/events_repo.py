import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event


class EventsRepo:
    """Data access for events table and idempotency helpers."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_uuid(self, event_uuid: UUID) -> Event | None:
        result = await self.session.execute(select(Event).where(Event.event_uuid == event_uuid))
        return result.scalar_one_or_none()

    async def insert_event(self, event: Event) -> Event:
        self.session.add(event)
        await self.session.flush()
        return event

    async def pull(self, site_id: int, since_seq: int, limit: int) -> list[Event]:
        stmt = (
            select(Event)
            .where(and_(Event.site_id == site_id, Event.server_seq > since_seq))
            .order_by(Event.server_seq)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_max_server_seq(self, site_id: int) -> int:
        stmt = select(Event.server_seq).where(Event.site_id == site_id).order_by(Event.server_seq.desc()).limit(1)
        result = await self.session.execute(stmt)
        max_seq = result.scalar_one_or_none()
        return int(max_seq or 0)

    @staticmethod
    def compute_payload_hash(payload: dict[str, Any]) -> str:
        canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
