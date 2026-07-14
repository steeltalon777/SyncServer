from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AuditItemEffect(Base):
    """One row per actual balance change.

    An effect captures the *delta* applied to a balance row as a result of
    submitting (or cancelling) a warehouse operation. Effects are written
    inside the same UoW transaction as the operation submit and are
    append-only.

    `inventory_subject_id` is mandatory (we always know which subject is
    affected). `item_id` may be null (e.g. for temporary items before they
    are approved). Snapshot fields store the name/SKU/subject_type at the
    moment of the effect, so that history survives deactivation or deletion
    of the domain entity.

    FK policy (Phase 1 baseline):
    - audit_event_id → audit_events.id RESTRICT  (audit is append-only)
    - operation_id → operations.id SET NULL      (operation may be hard-deleted in future)
    - inventory_subject_id → inventory_subjects.id RESTRICT (subject must exist for effect to be meaningful)
    - item_id → items.id RESTRICT                (history of an item must not vanish)
    - site_id → sites.id SET NULL                (sites are reference data)
    - caused_by_event_id → audit_events.id RESTRICT (chain reasoning is preserved)
    """

    __tablename__ = "audit_item_effects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_event_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("audit_events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    operation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operations.id", ondelete="SET NULL"),
        nullable=True,
    )
    inventory_subject_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inventory_subjects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    item_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=True,
    )
    item_name_snapshot: Mapped[str | None] = mapped_column(String(256), nullable=True)
    item_sku_snapshot: Mapped[str | None] = mapped_column(String(128), nullable=True)
    subject_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    site_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
    )
    quantity_before: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    quantity_after: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    effect_type: Mapped[str] = mapped_column(String(32), nullable=False)
    is_system_generated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        default=False,
    )
    caused_by_event_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("audit_events.id", ondelete="RESTRICT"),
        nullable=True,
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    audit_event = relationship("AuditEvent", foreign_keys=[audit_event_id])
    caused_by = relationship("AuditEvent", foreign_keys=[caused_by_event_id])
    inventory_subject = relationship("InventorySubject", foreign_keys=[inventory_subject_id])
    item = relationship("Item", foreign_keys=[item_id])
    site = relationship("Site", foreign_keys=[site_id])

    __table_args__ = (
        Index("ix_audit_item_effects_event_id", "audit_event_id"),
        Index("ix_audit_item_effects_inventory_subject_id", "inventory_subject_id"),
        Index("ix_audit_item_effects_item_id", "item_id"),
        Index("ix_audit_item_effects_site_id", "site_id"),
        Index("ix_audit_item_effects_operation_id", "operation_id"),
        Index("ix_audit_item_effects_effect_type", "effect_type"),
    )
