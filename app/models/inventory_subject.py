from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class InventorySubject(Base):
    __tablename__ = "inventory_subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 'catalog_item' or 'temporary_item'
    item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("items.id"), nullable=True)
    temporary_item_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("temporary_items.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    item = relationship("Item", foreign_keys=[item_id], back_populates="inventory_subject")
    temporary_item = relationship("TemporaryItem", foreign_keys=[temporary_item_id], back_populates="inventory_subject")

    __table_args__ = (
        UniqueConstraint("item_id", name="uq_inventory_subjects_item_id"),
        UniqueConstraint("temporary_item_id", name="uq_inventory_subjects_temporary_item_id"),
    )