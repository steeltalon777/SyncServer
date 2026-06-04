from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class IssueObjectCategory(Base):
    __tablename__ = "issue_object_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_key: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("issue_object_categories.id"), nullable=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    children: Mapped[list[IssueObjectCategory]] = relationship(
        "IssueObjectCategory",
        backref="parent",
        remote_side="IssueObjectCategory.id",
        cascade="all, delete-orphan",
        viewonly=True,
    )

    issue_objects: Mapped[list["IssueObject"]] = relationship(
        "IssueObject", back_populates="category", foreign_keys="IssueObject.category_id"
    )

    __table_args__ = (
        Index("uq_io_categories_root_normalized_key", "normalized_key", unique=True, postgresql_where=parent_id.is_(None)),
        Index("uq_io_categories_child_parent_normalized_key", "parent_id", "normalized_key", unique=True, postgresql_where=parent_id.isnot(None)),
        Index("ix_io_categories_normalized_key", "normalized_key"),
        Index("ix_io_categories_parent_id", "parent_id"),
        Index("ix_io_categories_deleted_at", "deleted_at"),
    )
