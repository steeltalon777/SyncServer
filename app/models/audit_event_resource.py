from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AuditEventResource(Base):
    """Many-to-many relationship table linking audit events to domain entities.

    An audit event may reference several resources with different relations
    (primary, merge_source, merge_target, generated, reparented, etc.).
    Each row records a single (event, resource, relation) triple.

    The combination of `resource_type` + `resource_id` is the symbolic
    reference to a domain entity (we keep them as strings because IDs can be
    integers or UUIDs depending on the entity).

    FK policy:
    - audit_event_id → audit_events.id RESTRICT (events are append-only)
    - No FK to the referenced resource (no domain dependency; enforced
      at the application layer; we do not enforce referential integrity
      because audit captures history of changes that may outlast the
      domain entity lifetime).
    """

    __tablename__ = "audit_event_resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_event_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("audit_events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(256), nullable=False)
    relation: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    snapshot_after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    audit_event = relationship("AuditEvent", foreign_keys=[audit_event_id])

    __table_args__ = (
        Index("ix_audit_event_resources_event_id", "audit_event_id"),
        Index("ix_audit_event_resources_type_id", "resource_type", "resource_id"),
    )
