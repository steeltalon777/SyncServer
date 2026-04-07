from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.models.event import Event
from app.repos.events_repo import EventsRepo
from app.schemas.sync import EventIn


ProcessStatus = Literal["accepted", "duplicate_same_payload", "uuid_collision"]


@dataclass(slots=True)
class ProcessResult:
    status: ProcessStatus
    event_uuid: UUID
    server_seq: int | None = None
    reason_code: str | None = None
    message: str | None = None


class EventIngestService:
    """Idempotent event ingestion by event_uuid + payload hash."""

    def __init__(self, events_repo: EventsRepo):
        self.events_repo = events_repo

    async def process_event(self, site_id: int, device_id: int | None, event_in: EventIn) -> ProcessResult:
        existing = await self.events_repo.get_by_uuid(event_in.event_uuid)
        payload = event_in.payload.model_dump(mode="json")
        payload_hash = self.events_repo.compute_payload_hash(payload)

        if existing is None:
            event = Event(
                event_uuid=event_in.event_uuid,
                site_id=site_id,
                device_id=device_id,
                event_type=event_in.event_type,
                event_datetime=event_in.event_datetime,
                schema_version=event_in.schema_version,
                payload=payload,
                payload_hash=payload_hash,
            )
            inserted = await self.events_repo.insert_event(event)
            return ProcessResult(status="accepted", event_uuid=inserted.event_uuid, server_seq=inserted.server_seq)

        if existing.payload_hash == payload_hash:
            return ProcessResult(
                status="duplicate_same_payload",
                event_uuid=existing.event_uuid,
                server_seq=existing.server_seq,
            )

        return ProcessResult(
            status="uuid_collision",
            event_uuid=event_in.event_uuid,
            reason_code="uuid_collision",
            message="event_uuid already exists with different payload",
        )
