from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMBaseModel

# ---------------------------------------------------------------------------
# Push response taxonomy (ADR-0016)
# ---------------------------------------------------------------------------
# Status of an individual event in a push batch:
# - "accepted":          event applied, server_seq assigned, advance cursor
# - "duplicate_same_payload": event_uuid + payload_hash already present (idempotent retry)
# - "uuid_collision":    event_uuid present with a different payload (conflict)
# - "processing_error":  internal exception while applying the event
# - "rejected":          server-side business rule violation (e.g. inactive item,
#                        insufficient balance, role not permitted) — framework
#                        ready, see ADR-0016; reserved for upcoming validation
#                        policy work
# HTTP-level statuses (not part of reason_code taxonomy, but documented here
# for completeness):
# - 401: auth_error      — invalid or missing token
# - 422: validation_error — payload fails schema validation
ReasonCode = Literal[
    "uuid_collision",
    "processing_error",
    "rejected",
]


class EventLine(BaseModel):
    item_id: int
    qty: Decimal = Field(max_digits=18, decimal_places=3)
    batch: str | None = None


class EventPayload(BaseModel):
    doc_id: str | None = None
    doc_type: str | None = None
    comment: str | None = None
    lines: list[EventLine] = Field(default_factory=list)


class EventIn(BaseModel):
    event_uuid: UUID
    event_type: str
    event_datetime: datetime
    schema_version: int = 1
    payload: EventPayload


class PushRequest(BaseModel):
    site_id: int
    device_id: int
    batch_id: UUID
    events: list[EventIn] = Field(default_factory=list)


class AcceptedEvent(ORMBaseModel):
    event_uuid: UUID
    server_seq: int


class DuplicateEvent(ORMBaseModel):
    event_uuid: UUID
    server_seq: int


class RejectedEvent(ORMBaseModel):
    event_uuid: UUID
    reason_code: ReasonCode
    message: str


class PushResponse(ORMBaseModel):
    accepted: list[AcceptedEvent] = Field(default_factory=list)
    duplicates: list[DuplicateEvent] = Field(default_factory=list)
    rejected: list[RejectedEvent] = Field(default_factory=list)
    server_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    server_seq_upto: int = 0
    # Counters used by the route layer to update sync_state.
    # Keys: accepted_count, duplicate_count, rejected_count, conflict_count,
    # last_error, max_server_seq. None when produced outside SyncService.
    summary: dict | None = None

    # See module docstring and ReasonCode for the full taxonomy. Client
    # behaviour per status:
    # - accepted       → drop from outbox, advance last_sequence_number
    # - duplicates[]   → drop from outbox (already applied)
    # - rejected[*]    → surface to user, drop from outbox, log last_error
    # - conflict (uuid_collision) → keep in outbox, ask user to resolve


class PingRequest(BaseModel):
    site_id: int
    device_id: int
    last_server_seq: int | None = None
    outbox_count: int = 0
    client_time: datetime | None = None


class PingResponse(ORMBaseModel):
    server_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    server_seq_upto: int = 0
    backoff_seconds: int = 0


class PullRequest(BaseModel):
    site_id: int
    device_id: int
    since_seq: int = 0
    limit: int = Field(default=200, ge=1, le=1000)


class PullEvent(ORMBaseModel):
    event_uuid: UUID
    server_seq: int
    event_type: str
    event_datetime: datetime
    schema_version: int
    payload: EventPayload


class PullResponse(ORMBaseModel):
    events: list[PullEvent] = Field(default_factory=list)
    server_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    server_seq_upto: int = 0
    next_since_seq: int = 0


class BootstrapSyncRequest(BaseModel):
    site_id: int = 0
    device_id: int = 0


class BootstrapData(BaseModel):
    """Данные начальной загрузки: доступные сайты, каталоги, настройки синхронизации."""
    available_sites: list[dict] = Field(default_factory=list)
    protocol_version: str = "1.0"
    settings: dict = Field(default_factory=dict)


class BootstrapSyncResponse(ORMBaseModel):
    server_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    protocol_version: str = "1.0"
    is_root: bool = False
    root_user: dict | None = None
    root_role: str | None = None
    device_id: int | None = None
    device_registered: bool = False
    message: str = ""
    bootstrap_data: BootstrapData | None = None


class SyncStatusResponse(ORMBaseModel):
    """Per-device sync state snapshot (ADR-0016).

    Returned by ``GET /api/v1/sync/status/{device_id}``.

    ``behind_by = max(0, server_seq_upto - last_sequence_number)`` measures
    how many events the device has not yet pulled.
    """

    device_id: int
    last_sequence_number: int
    last_sync_at: datetime | None
    status: str
    server_seq_upto: int
    behind_by: int
