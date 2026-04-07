from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMBaseModel

ReasonCode = Literal["uuid_collision", "processing_error", "validation_error"]


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
