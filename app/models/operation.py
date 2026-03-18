from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


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
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)

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

    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    submitted_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancelled_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

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

    __table_args__ = (
        CheckConstraint(
            "operation_type IN ('RECEIVE', 'WRITE_OFF', 'MOVE')",
            name="ck_operations_type",
        ),
        CheckConstraint(
            "status IN ('draft', 'submitted', 'cancelled')",
            name="ck_operations_status",
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
    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id"),
        nullable=False,
    )
    qty: Mapped[int] = mapped_column(nullable=False)
    batch: Mapped[str | None] = mapped_column(String(100), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    operation: Mapped[Operation] = relationship("Operation", back_populates="lines")
    item = relationship("Item")

    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_operation_lines_qty_positive"),
    )