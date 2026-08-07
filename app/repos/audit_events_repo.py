from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import joinedload

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent
from app.models.audit_event_resource import AuditEventResource
from app.models.audit_item_effect import AuditItemEffect


class AuditEventsRepo:
    """Repository for audit events (append-only).

    Phase 1 (TZ-AUDIT_BACKEND_FOUNDATION) adds:
    - resource / effect inserts and reads
    - parent_event_id / correlation_id list filters
    - find_by_external_event_id for idempotency lookups (Phase 2 hook)
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # ─────────────────────────────────────────────────────────────────
    # Events
    # ─────────────────────────────────────────────────────────────────

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
        correlation_id: str | None = None,
        parent_event_id: UUID | None = None,
        outcome: str | None = None,
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
        if correlation_id is not None:
            where_clauses.append(AuditEvent.correlation_id == correlation_id)
        if parent_event_id is not None:
            where_clauses.append(AuditEvent.parent_event_id == parent_event_id)
        if outcome is not None:
            where_clauses.append(AuditEvent.outcome == outcome)
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
                joinedload(AuditEvent.parent_event),
            )
            .where(AuditEvent.event_id == event_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_correlation_id(
        self,
        correlation_id: str,
        *,
        page: int = 1,
        page_size: int = 500,
    ) -> list[AuditEvent]:
        """Return all events that share the same batch correlation id."""
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.correlation_id == correlation_id)
            .order_by(AuditEvent.created_at.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_by_parent_event_id(
        self,
        parent_event_id: UUID,
    ) -> list[AuditEvent]:
        """Return direct children of a parent event (e.g. ADJUSTMENT submits under a merge)."""
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.parent_event_id == parent_event_id)
            .order_by(AuditEvent.created_at.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def find_by_external_event_id(self, external_event_id: str) -> AuditEvent | None:
        """Find a previously-received event by idempotency key (Phase 2 hook)."""
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.external_event_id == external_event_id)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def find_latest_event_for_entity(
        self,
        *,
        event_type: str,
        entity_type: str,
        entity_id: str,
        outcome: str = "success",
    ) -> AuditEvent | None:
        """Return newest matching audit event for (event_type, entity).

        Used to wire `operation.restore.parent_event_id` to the latest
        successful `operation.cancel` of the same operation. Deterministic
        ordering: newest `created_at`, tiebreaker on `id` descending.
        ADR-0028 §3.1 specifies this lookup contract.
        """
        stmt = (
            select(AuditEvent)
            .where(
                AuditEvent.event_type == event_type,
                AuditEvent.entity_type == entity_type,
                AuditEvent.entity_id == entity_id,
                AuditEvent.outcome == outcome,
            )
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    # ─────────────────────────────────────────────────────────────────
    # Resources (audit_event_resources)
    # ─────────────────────────────────────────────────────────────────

    async def insert_resource(
        self,
        *,
        audit_event_id: int,
        resource_type: str,
        resource_id: str,
        relation: str,
        snapshot_before: dict | None = None,
        snapshot_after: dict | None = None,
    ) -> AuditEventResource:
        """Append a resource link to an existing audit event."""
        resource = AuditEventResource(
            audit_event_id=audit_event_id,
            resource_type=resource_type,
            resource_id=resource_id,
            relation=relation,
            snapshot_before=snapshot_before,
            snapshot_after=snapshot_after,
        )
        self.session.add(resource)
        await self.session.flush()
        return resource

    async def list_resources(self, audit_event_id: int) -> list[AuditEventResource]:
        stmt = (
            select(AuditEventResource)
            .where(AuditEventResource.audit_event_id == audit_event_id)
            .order_by(AuditEventResource.id.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_resources_for_entity(
        self,
        *,
        resource_type: str,
        resource_id: str,
    ) -> list[AuditEventResource]:
        """Find audit resources pointing at a given entity, newest first."""
        stmt = (
            select(AuditEventResource)
            .where(
                AuditEventResource.resource_type == resource_type,
                AuditEventResource.resource_id == resource_id,
            )
            .order_by(AuditEventResource.id.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    # ─────────────────────────────────────────────────────────────────
    # Item effects (audit_item_effects)
    # ─────────────────────────────────────────────────────────────────

    async def insert_effect(self, effect: AuditItemEffect) -> AuditItemEffect:
        """Append an item balance effect to the journal."""
        self.session.add(effect)
        await self.session.flush()
        return effect

    async def list_effects(self, audit_event_id: int) -> list[AuditItemEffect]:
        stmt = (
            select(AuditItemEffect)
            .where(AuditItemEffect.audit_event_id == audit_event_id)
            .order_by(AuditItemEffect.id.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_effects_by_item(
        self,
        item_id: int,
        *,
        site_id: int | None = None,
        effect_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        include_system: bool = True,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditItemEffect], int]:
        """Paginated effect lookup by item. Filters compose with AND.

        By default both user and system effects are returned. Setting
        `include_system=False` hides merge write-offs / receipts so the
        caller can show a clean user-driven timeline.
        """
        where_clauses = [AuditItemEffect.item_id == item_id]
        if site_id is not None:
            where_clauses.append(AuditItemEffect.site_id == site_id)
        if effect_type is not None:
            where_clauses.append(AuditItemEffect.effect_type == effect_type)
        if date_from is not None:
            where_clauses.append(AuditItemEffect.created_at >= date_from)
        if date_to is not None:
            where_clauses.append(AuditItemEffect.created_at <= date_to)
        if not include_system:
            where_clauses.append(AuditItemEffect.is_system_generated.is_(False))

        count_stmt = select(func.count()).select_from(AuditItemEffect).where(*where_clauses)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(AuditItemEffect)
            .where(*where_clauses)
            .order_by(AuditItemEffect.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list((await self.session.execute(stmt)).scalars().all())
        return items, int(total)

    async def get_effects_by_subject(
        self,
        inventory_subject_id: int,
        *,
        site_id: int | None = None,
        effect_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        include_system: bool = True,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditItemEffect], int]:
        """Paginated effect lookup by inventory subject. Used for temporary items."""
        where_clauses = [AuditItemEffect.inventory_subject_id == inventory_subject_id]
        if site_id is not None:
            where_clauses.append(AuditItemEffect.site_id == site_id)
        if effect_type is not None:
            where_clauses.append(AuditItemEffect.effect_type == effect_type)
        if date_from is not None:
            where_clauses.append(AuditItemEffect.created_at >= date_from)
        if date_to is not None:
            where_clauses.append(AuditItemEffect.created_at <= date_to)
        if not include_system:
            where_clauses.append(AuditItemEffect.is_system_generated.is_(False))

        count_stmt = select(func.count()).select_from(AuditItemEffect).where(*where_clauses)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(AuditItemEffect)
            .where(*where_clauses)
            .order_by(AuditItemEffect.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list((await self.session.execute(stmt)).scalars().all())
        return items, int(total)
