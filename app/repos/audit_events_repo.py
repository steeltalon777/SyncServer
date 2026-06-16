from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import joinedload

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent


class AuditEventsRepo:
    """Repository for audit events (append-only)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert(self, event: AuditEvent) -> AuditEvent:
        """Persist a new audit event."""
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_events(
        self,
        *,
        event_type: str | None = None,
        actor_user_id: UUID | None = None,
        site_id: int | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditEvent], int]:
        """List audit events with optional filters. Returns (items, total_count)."""
        where_clauses: list = []

        if event_type is not None:
            where_clauses.append(AuditEvent.event_type == event_type)
        if actor_user_id is not None:
            where_clauses.append(AuditEvent.actor_user_id == actor_user_id)
        if site_id is not None:
            where_clauses.append(AuditEvent.site_id == site_id)
        if entity_type is not None:
            where_clauses.append(AuditEvent.entity_type == entity_type)
        if entity_id is not None:
            where_clauses.append(AuditEvent.entity_id == entity_id)
        if date_from is not None:
            where_clauses.append(AuditEvent.created_at >= date_from)
        if date_to is not None:
            where_clauses.append(AuditEvent.created_at <= date_to)

        # Count
        count_stmt = select(func.count()).select_from(AuditEvent)
        if where_clauses:
            count_stmt = count_stmt.where(*where_clauses)
        total_count = (await self.session.execute(count_stmt)).scalar_one()

        # Fetch page
        stmt: Select = select(AuditEvent)
        if where_clauses:
            stmt = stmt.where(*where_clauses)
        stmt = (
            stmt.order_by(AuditEvent.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list((await self.session.execute(stmt)).scalars().all())

        return items, total_count

    async def get_by_id(self, event_id: UUID) -> AuditEvent | None:
        """Get a single audit event by event_id (UUID)."""
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.event_id == event_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_full(self, event_id: UUID) -> AuditEvent | None:
        """Get a single audit event by event_id with eager-loaded relationships."""
        stmt = (
            select(AuditEvent)
            .options(
                joinedload(AuditEvent.actor_user),
                joinedload(AuditEvent.actor_device),
                joinedload(AuditEvent.site),
            )
            .where(AuditEvent.event_id == event_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
