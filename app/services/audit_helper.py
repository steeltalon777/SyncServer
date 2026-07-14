from __future__ import annotations

from uuid import UUID

from app.models.audit_event import AuditEvent
from app.services.uow import UnitOfWork


# Allowed values for source_client; anything else is normalised to "unknown".
ALLOWED_SOURCE_CLIENTS = {"web", "desktop", "mobile", "cli"}


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
    # Phase 1 (TZ-AUDIT_BACKEND_FOUNDATION §7.1) extended fields.
    # event_version defaults to 2: events whose `changes` conforms to the
    # documented schema. Legacy events created before this column existed
    # carry event_version=1 (free-form changes).
    event_version: int = 2,
    outcome: str | None = None,
    correlation_id: str | None = None,
    parent_event_id: UUID | None = None,
    source_client: str | None = None,
    actor_username_snapshot: str | None = None,
    external_event_id: str | None = None,
) -> AuditEvent:
    """Create and persist an audit event within the current UoW transaction.

    Fire-and-forget within the same UoW: lightweight insert that does not
    block the main business operation. The event is NOT visible to other
    transactions until the UoW commits.

    `correlation_id` is taken from the explicit parameter or, when unset,
    from the UoW-scoped context (`uow.batch_correlation_id`). This lets
    the catalog batch flow populate correlation_id without changing the
    signature of every service helper that ends up writing audit events.
    """
    if correlation_id is None:
        correlation_id = getattr(uow, "batch_correlation_id", None)

    if source_client is not None and source_client not in ALLOWED_SOURCE_CLIENTS:
        # Untrusted client header; do not leak arbitrary values into the
        # journal — fall back to "unknown" so analysts can still filter.
        source_client = "unknown"

    event = AuditEvent(
        event_type=event_type,
        event_version=event_version,
        actor_user_id=actor_user_id,
        actor_device_id=actor_device_id,
        site_id=site_id,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        changes=changes,
        request_id=request_id,
        outcome=outcome,
        correlation_id=correlation_id,
        parent_event_id=parent_event_id,
        source_client=source_client,
        actor_username_snapshot=actor_username_snapshot,
        external_event_id=external_event_id,
    )
    return await uow.audit_events.insert(event)
