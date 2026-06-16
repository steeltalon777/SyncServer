from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), unique=True, default=uuid4, nullable=False,
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # relationships (optional, for read convenience)
    actor_user = relationship("User", foreign_keys=[actor_user_id])
    actor_device = relationship("Device", foreign_keys=[actor_device_id])
    site = relationship("Site", foreign_keys=[site_id])

    __table_args__ = (
        Index("ix_audit_events_actor_user_id", "actor_user_id"),
        Index("ix_audit_events_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_audit_events_site_id", "site_id"),
        Index("ix_audit_events_created_at", "created_at"),
    )
