from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AuditEvent(Base):
    """Append-only journal of business events.

    Phase 1 extension (TZ-AUDIT_BACKEND_FOUNDATION):
    - event_version=2 marks events whose `changes` JSONB conforms to the
      documented schema. Old events (created before the migration) have
      event_version=1 and may have free-form `changes`.
    - outcome distinguishes successful vs partial vs failed events.
    - correlation_id groups events belonging to the same batch.
    - parent_event_id creates a child-of relationship between merge events
      and the system ADJUSTMENT operations they generate.
    - credential_kind / credential_fingerprint / external_event_id are
      Phase 2 hooks: columns are created here, populated later when
      SyncServer starts accepting audit events from the auth outbox.
    - source_client / actor_username_snapshot carry informational metadata
      about who/what emitted the event without bloating transactional data.
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), unique=True, default=uuid4, nullable=False,
    )
    event_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="2",
        default=2,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    actor_device_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("devices.id"),
        nullable=True,
    )
    site_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sites.id"),
        nullable=True,
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(256), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    changes: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)

    # Phase 1: documented in TZ-AUDIT_BACKEND_FOUNDATION §7.1
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("audit_events.event_id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Phase 2 hooks — column added now, populated later.
    credential_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    credential_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)

    source_client: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actor_username_snapshot: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # relationships (optional, for read convenience)
    actor_user = relationship("User", foreign_keys=[actor_user_id])
    actor_device = relationship("Device", foreign_keys=[actor_device_id])
    site = relationship("Site", foreign_keys=[site_id])
    parent_event = relationship("AuditEvent", foreign_keys=[parent_event_id], remote_side="AuditEvent.event_id")

    __table_args__ = (
        Index("ix_audit_events_actor_user_id", "actor_user_id"),
        Index("ix_audit_events_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_audit_events_site_id", "site_id"),
        Index("ix_audit_events_created_at", "created_at"),
        Index("ix_audit_events_correlation_id", "correlation_id"),
        Index("ix_audit_events_parent_event_id", "parent_event_id"),
        Index("ix_audit_events_outcome", "outcome"),
        UniqueConstraint("external_event_id", name="uq_audit_events_external_event_id"),
    )
