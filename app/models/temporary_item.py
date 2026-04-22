from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TemporaryItem(Base):
    __tablename__ = "temporary_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("items.id"), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit_id: Mapped[int] = mapped_column(Integer, ForeignKey("units.id"), nullable=False)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("items.id"), nullable=True)
    resolution_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    item = relationship("Item", foreign_keys=[item_id], back_populates="temporary_item")
    resolved_item = relationship("Item", foreign_keys=[resolved_item_id])
    unit = relationship("Unit")
    category = relationship("Category")

    __table_args__ = (
        UniqueConstraint("item_id", name="uq_temporary_items_item_id"),
        Index("ix_temporary_items_status", "status"),
        Index("ix_temporary_items_created_by_user_id", "created_by_user_id"),
        Index("ix_temporary_items_normalized_name", "normalized_name"),
    )
