from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

import sqlalchemy as sa
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
    issue_object_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("issue_objects.id"),
        nullable=True,
    )
    issue_object_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)

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

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deleted_by_user_id: Mapped[UUID | None] = mapped_column(
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

    display_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
        default=1,
    )
    machine_last_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Warehouse 3.2: dedicated web idempotency columns (separate from machine sync flow)
    client_request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    client_request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Phase 1: TZ-AUDIT_BACKEND_FOUNDATION §7.4 — system vs user origin.
    # origin="system" is set when the operation was created automatically as
    # part of a merge (item.merge, temporary resolution, review merge).
    # system_reason categorises the system path.
    # initiated_by_user_id is the responsible user (the one who triggered
    # the merge flow that ultimately produced this system ADJUSTMENT).
    origin: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="user",
        default="user",
    )
    system_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    initiated_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )

    # TZ-SOURCE_DOCUMENT_OPERATION_INTAKE_HARDENING: source-document flow marker
    creation_source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="legacy",
        default="legacy",
    )
    # Значения:
    # - "manual" — ручное создание через UI (POST /operations без temporary_item)
    # - "source_document" — через dedicated endpoint (POST /operations/from-source-document)
    # - "system" — служебная (merge, review resolution, system ADJUSTMENT)
    # - "legacy" — существующие операции до этого TZ (default при backfill)

    # Ref на source документ (например, "invoice-2026-07-21-001")
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)

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
        # Partial unique index for web idempotency (Warehouse 3.2)
        sa.Index(
            "ix_operations_client_request_id",
            "created_by_user_id",
            "client_request_id",
            postgresql_where=sa.text("client_request_id IS NOT NULL"),
            unique=True,
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

    # SOURCE snapshot (от исходного документа, фиксируется на draft)
    source_item_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_item_sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_unit_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_category_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Historical snapshots (catalog snapshot, frozen at submit)
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
        sa.JSON(none_as_null=True),
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

    @property
    def resolution_mode(self) -> Literal["existing_item", "inline_item"]:
        """existing_item: item_id != null, temporary_draft_payload = null
        inline_item: temporary_draft_payload != null (item_id = null до submit)
        """
        if self.temporary_draft_payload is not None:
            return "inline_item"
        return "existing_item"

    __table_args__ = (
        CheckConstraint("qty <> 0", name="ck_operation_lines_qty_non_zero"),
        CheckConstraint("accepted_qty >= 0", name="ck_operation_lines_accepted_qty_non_negative"),
        CheckConstraint("lost_qty >= 0", name="ck_operation_lines_lost_qty_non_negative"),
    )
