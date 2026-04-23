from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship

from app.models.base import Base


class PendingAcceptanceBalance(Base):
    __tablename__ = "pending_acceptance_balances"

    operation_line_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("operation_lines.id"),
        primary_key=True,
    )
    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operations.id"),
        nullable=False,
    )
    destination_site_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sites.id"),
        nullable=False,
    )
    source_site_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sites.id"),
        nullable=True,
    )
    inventory_subject_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inventory_subjects.id"),
        nullable=False,
    )
    item_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("items.id"),
        nullable=True,
    )
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint("qty >= 0", name="ck_pending_acceptance_qty_non_negative"),
    )

    inventory_subject = relationship("InventorySubject")
    item = relationship("Item")


class LostAssetBalance(Base):
    __tablename__ = "lost_asset_balances"

    operation_line_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("operation_lines.id"),
        primary_key=True,
    )
    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operations.id"),
        nullable=False,
    )
    site_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sites.id"),
        nullable=False,
    )
    source_site_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sites.id"),
        nullable=True,
    )
    inventory_subject_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inventory_subjects.id"),
        nullable=False,
    )
    item_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("items.id"),
        nullable=True,
    )
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint("qty >= 0", name="ck_lost_asset_qty_non_negative"),
    )

    inventory_subject = relationship("InventorySubject")
    item = relationship("Item")


class IssuedAssetBalance(Base):
    __tablename__ = "issued_asset_balances"

    recipient_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("recipients.id"),
        primary_key=True,
    )
    inventory_subject_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inventory_subjects.id"),
        primary_key=True,
    )
    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id"),
        nullable=True,
    )
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint("qty >= 0", name="ck_issued_asset_qty_non_negative"),
    )

    inventory_subject = relationship("InventorySubject")
    item = relationship("Item")


class OperationAcceptanceAction(Base):
    __tablename__ = "operation_acceptance_actions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("operations.id"),
        nullable=False,
    )
    operation_line_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("operation_lines.id"),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    performed_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    recipient_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("recipients.id"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_operation_acceptance_actions_qty_positive"),
        CheckConstraint(
            "action_type IN ('accept', 'mark_lost', 'found_to_destination', 'return_to_source', 'write_off')",
            name="ck_operation_acceptance_actions_type",
        ),
    )
