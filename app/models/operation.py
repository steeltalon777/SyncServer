from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

import sqlalchemy
from app.models.base import Base
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Operation(Base):
    __tablename__ = "operations"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    site_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sites.id"),
        nullable=False,
    )

    operation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="draft",
        server_default="draft",
    )

    source_site_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sites.id"),
        nullable=True,
    )
    destination_site_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sites.id"),
        nullable=True,
    )

    issued_to_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    issued_to_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("recipients.id"),
        nullable=True,
    )
    recipient_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )

    created_at = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    effective_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    submitted_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancelled_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )

    acceptance_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    acceptance_state: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="not_required",
        server_default="not_required",
    )
    acceptance_resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    acceptance_resolved_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
        default=1,
    )
    machine_last_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    lines: Mapped[list["OperationLine"]] = relationship(
        "OperationLine",
        back_populates="operation",
        cascade="all, delete-orphan",
    )

    site = relationship(
        "Site",
        back_populates="operations",
        foreign_keys=[site_id],
    )
    source_site = relationship(
        "Site",
        back_populates="source_operations",
        foreign_keys=[source_site_id],
    )
    destination_site = relationship(
        "Site",
        back_populates="destination_operations",
        foreign_keys=[destination_site_id],
    )
    documents: Mapped[list["Document"]] = relationship(
        "Document",
        secondary="document_operations",
        back_populates="operations",
        overlaps="document_operations_assoc,document,operation",
    )
    document_operations_assoc: Mapped[list["DocumentOperation"]] = relationship(
        "DocumentOperation",
        back_populates="operation",
        cascade="all, delete-orphan",
        overlaps="documents,operations",
    )

    __table_args__ = (
        CheckConstraint(
            "operation_type IN ('RECEIVE', 'EXPENSE', 'WRITE_OFF', 'MOVE', 'ADJUSTMENT', 'ISSUE', 'ISSUE_RETURN')",
            name="ck_operations_type",
        ),
        CheckConstraint(
            "status IN ('draft', 'submitted', 'cancelled')",
            name="ck_operations_status",
        ),
        CheckConstraint(
            "acceptance_state IN ('not_required', 'pending', 'in_progress', 'resolved')",
            name="ck_operations_acceptance_state",
        ),
    )


class OperationLine(Base):
    __tablename__ = "operation_lines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operations.id"),
        nullable=False,
    )

    line_number: Mapped[int] = mapped_column(nullable=False)

    inventory_subject_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("inventory_subjects.id"),
        nullable=True,
    )
    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id"),
        nullable=True,
    )

    qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        nullable=False,
    )
    accepted_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        nullable=False,
        default=0,
        server_default="0",
    )
    lost_qty: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        nullable=False,
        default=0,
        server_default="0",
    )

    batch: Mapped[str | None] = mapped_column(String(100), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Historical snapshots
    item_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    item_sku_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit_name_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit_symbol_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    category_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Deferred temporary creation payload (JSON)
    # Хранит данные для materialization temporary сущностей при submit.
    # Пока поле не null — строка считается draft-temporary.
    # После materialization на submit поле очищается.
    temporary_draft_payload: Mapped[dict | None] = mapped_column(
        "temporary_draft_payload",
        sqlalchemy.JSON(none_as_null=True),
        nullable=True,
        default=None,
    )

    operation: Mapped[Operation] = relationship("Operation", back_populates="lines")
    inventory_subject = relationship("InventorySubject")
    item = relationship("Item")

    @property
    def subject_type(self) -> str | None:
        subject = getattr(self, "inventory_subject", None)
        return None if subject is None else subject.subject_type

    @property
    def temporary_item_id(self) -> int | None:
        subject = getattr(self, "inventory_subject", None)
        if subject is not None and subject.temporary_item_id is not None:
            return subject.temporary_item_id
        temporary_item = getattr(self.item, "temporary_item", None)
        return None if temporary_item is None else temporary_item.id

    @property
    def temporary_item_status(self) -> str | None:
        subject = getattr(self, "inventory_subject", None)
        temporary_item = None if subject is None else getattr(subject, "temporary_item", None)
        if temporary_item is None:
            temporary_item = getattr(self.item, "temporary_item", None)
        return None if temporary_item is None else temporary_item.status

    @property
    def resolved_item_id(self) -> int | None:
        subject = getattr(self, "inventory_subject", None)
        temporary_item = None if subject is None else getattr(subject, "temporary_item", None)
        if temporary_item is None:
            temporary_item = getattr(self.item, "temporary_item", None)
        return None if temporary_item is None else temporary_item.resolved_item_id

    @property
    def resolved_item_name(self) -> str | None:
        subject = getattr(self, "inventory_subject", None)
        temporary_item = None if subject is None else getattr(subject, "temporary_item", None)
        if temporary_item is None:
            temporary_item = getattr(self.item, "temporary_item", None)
        resolved_item = None if temporary_item is None else getattr(temporary_item, "resolved_item", None)
        return None if resolved_item is None else resolved_item.name

    @property
    def is_draft_temporary(self) -> bool:
        """Returns True if this line has a deferred temporary payload not yet materialized."""
        return self.temporary_draft_payload is not None

    __table_args__ = (
        CheckConstraint("qty <> 0", name="ck_operation_lines_qty_non_zero"),
        CheckConstraint("accepted_qty >= 0", name="ck_operation_lines_accepted_qty_non_negative"),
        CheckConstraint("lost_qty >= 0", name="ck_operation_lines_lost_qty_non_negative"),
    )
