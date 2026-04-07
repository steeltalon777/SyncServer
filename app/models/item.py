from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("categories.id"),
        nullable=False,
    )
    unit_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("units.id"),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )
    hashtags: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=list,
    )
    source_system: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    import_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    machine_last_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    category = relationship("Category")
    unit = relationship("Unit")

    __table_args__ = (
        Index("ix_items_category_id", "category_id"),
        Index("ix_items_normalized_name", "normalized_name"),
        Index("ix_items_import_batch_id", "import_batch_id"),
        Index("ix_items_unit_id", "unit_id"),
        Index("ix_items_updated_at", "updated_at"),
        Index("idx_items_hashtags", "hashtags", postgresql_using="gin"),
    )
