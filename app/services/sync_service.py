from __future__ import annotations

from dataclasses import asdict, dataclass
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


@dataclass(slots=True)
class PushSummary:
    """Lightweight summary of a push batch outcome for sync_state updates.

    The route layer converts this into a SyncStateRepo.upsert call.
    """

    accepted_count: int = 0
    duplicate_count: int = 0
    rejected_count: int = 0
    conflict_count: int = 0
    last_error: str | None = None
    max_server_seq: int = 0


class SyncService:
    """High-level sync workflow without HTTP layer concerns.

    ``process_push`` returns a :class:`PushResponse` with a ``summary``
    attribute (dict) carrying the counters used by the route layer to update
    ``sync_state``. The combined shape preserves backward compatibility with
    call sites that read ``.accepted``/``.duplicates``/``.rejected`` directly.
    """

    async def process_push(
        self, uow: UnitOfWork, request: PushRequest
    ) -> PushResponse:
        response = PushResponse(server_time=datetime.now(UTC))
        ingest = EventIngestService(uow.events)
        summary = PushSummary()

        for event_in in request.events:
            result = await ingest.process_event(
                site_id=request.site_id,
                device_id=request.device_id,
                event_in=event_in,
            )

            if result.status == "accepted":
                response.accepted.append(
                    AcceptedEvent(event_uuid=result.event_uuid, server_seq=result.server_seq or 0)
                )
                response.server_seq_upto = max(response.server_seq_upto, result.server_seq or 0)
                summary.accepted_count += 1
                summary.max_server_seq = max(summary.max_server_seq, result.server_seq or 0)
                continue

            if result.status == "duplicate_same_payload":
                response.duplicates.append(
                    DuplicateEvent(event_uuid=result.event_uuid, server_seq=result.server_seq or 0)
                )
                response.server_seq_upto = max(response.server_seq_upto, result.server_seq or 0)
                summary.duplicate_count += 1
                summary.max_server_seq = max(summary.max_server_seq, result.server_seq or 0)
                continue

            response.rejected.append(
                RejectedEvent(
                    event_uuid=result.event_uuid,
                    reason_code="uuid_collision",
                    message=result.message or "event_uuid already exists with different payload",
                )
            )
            summary.conflict_count += 1
            summary.last_error = (
                f"conflict: event_uuid={result.event_uuid} payload mismatch"
            )

        summary.rejected_count = len(response.rejected)
        # Mirror server_seq_upto into the summary for the route layer.
        summary.max_server_seq = max(summary.max_server_seq, response.server_seq_upto)

        # Attach counters as a dict (Pydantic-friendly) for the route layer
        # to read without breaking existing direct-access call sites.
        response.summary = asdict(summary)

        return response
