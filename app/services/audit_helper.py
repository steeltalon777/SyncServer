from __future__ import annotations

from uuid import UUID

from app.models.audit_event import AuditEvent
from app.services.uow import UnitOfWork


async def record_audit_event(
    uow: UnitOfWork,
    *,
    event_type: str,
    actor_user_id: UUID | None,
    actor_device_id: int | None = None,
    site_id: int | None = None,
    entity_type: str,
    entity_id: str,
    summary: str,
    changes: dict | None = None,
    request_id: str | None = None,
) -> AuditEvent:
    """Create and persist an audit event within the current UoW transaction.

    Fire-and-forget within the same UoW: lightweight insert that does not
    block the main business operation.
    """
    event = AuditEvent(
        event_type=event_type,
        actor_user_id=actor_user_id,
        actor_device_id=actor_device_id,
        site_id=site_id,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        changes=changes,
        request_id=request_id,
    )
    return await uow.audit_events.insert(event)
