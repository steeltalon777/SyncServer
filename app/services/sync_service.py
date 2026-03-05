from datetime import UTC, datetime

from app.schemas.sync import (
    AcceptedEvent,
    DuplicateEvent,
    PushRequest,
    PushResponse,
    RejectedEvent,
)
from app.services.event_ingest import EventIngestService
from app.services.uow import UnitOfWork


class SyncService:
    """High-level sync workflow without HTTP layer concerns."""

    async def process_push(self, uow: UnitOfWork, request: PushRequest) -> PushResponse:
        response = PushResponse(server_time=datetime.now(UTC))
        ingest = EventIngestService(uow.events)

        for event_in in request.events:
            result = await ingest.process_event(
                site_id=request.site_id,
                device_id=request.device_id,
                event_in=event_in,
            )

            if result.status == "accepted":
                response.accepted.append(AcceptedEvent(event_uuid=result.event_uuid, server_seq=result.server_seq or 0))
                response.server_seq_upto = max(response.server_seq_upto, result.server_seq or 0)
                continue

            if result.status == "duplicate_same_payload":
                response.duplicates.append(DuplicateEvent(event_uuid=result.event_uuid, server_seq=result.server_seq or 0))
                response.server_seq_upto = max(response.server_seq_upto, result.server_seq or 0)
                continue

            response.rejected.append(
                RejectedEvent(
                    event_uuid=result.event_uuid,
                    reason_code="uuid_collision",
                    message=result.message or "event_uuid already exists with different payload",
                )
            )

        return response
