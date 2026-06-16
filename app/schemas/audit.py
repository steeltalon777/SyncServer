from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import ORMBaseModel


class AuditEventResponse(ORMBaseModel):
    """Response schema for a single audit event."""

    id: int
    event_id: UUID
    event_type: str
    actor_user_id: UUID | None = None
    actor_device_id: int | None = None
    site_id: int | None = None
    entity_type: str
    entity_id: str
    summary: str
    changes: dict | None = None
    request_id: str | None = None
    created_at: datetime


class AuditEventListResponse(BaseModel):
    """Paginated response for audit events list."""

    items: list[AuditEventResponse]
    total_count: int
    page: int
    page_size: int
