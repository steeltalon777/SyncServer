from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class IssueObject(Base):
    __tablename__ = "issue_objects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    object_type: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="person",
        server_default="person",
    )
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    normalized_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    merged_into_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("issue_objects.id"),
        nullable=True,
    )
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
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    aliases: Mapped[list[IssueObjectAlias]] = relationship(
        "IssueObjectAlias",
        back_populates="issue_object",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "object_type IN ('person', 'base', 'vehicle', 'department', 'contractor', 'other_object', 'system_repo')",
            name="ck_issue_objects_type",
        ),
        Index("ix_issue_objects_display_name", "display_name"),
        Index("ix_issue_objects_deleted_at", "deleted_at"),
    )


class IssueObjectAlias(Base):
    __tablename__ = "issue_object_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_object_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("issue_objects.id"),
        nullable=False,
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    issue_object: Mapped[IssueObject] = relationship("IssueObject", back_populates="aliases")

    __table_args__ = (
        Index("ix_issue_object_aliases_issue_object_id", "issue_object_id"),
    )
