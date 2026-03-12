from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Operation(Base):
    __tablename__ = "operations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    operation_uuid: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True, nullable=False)
    site_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("sites.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    submitted_by_user_id: Mapped[int | None] = mapped_column(nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancelled_by_user_id: Mapped[int | None] = mapped_column(nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    lines: Mapped[list[OperationLine]] = relationship(
        "OperationLine", back_populates="operation", cascade="all, delete-orphan"
    )
    site = relationship("Site", back_populates="operations")

    __table_args__ = (
        CheckConstraint(
            "type IN ('RECEIVE', 'WRITE_OFF', 'MOVE', 'ISSUE')",
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
    operation_id: Mapped[int] = mapped_column(ForeignKey("operations.id"), nullable=False)
    line_number: Mapped[int] = mapped_column(nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    source_site_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("sites.id"), nullable=True)
    target_site_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("sites.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    operation: Mapped[Operation] = relationship("Operation", back_populates="lines")
    item = relationship("Item")
    source_site = relationship("Site", foreign_keys=[source_site_id])
    target_site = relationship("Site", foreign_keys=[target_site_id])

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_operation_lines_quantity_positive"),
    )