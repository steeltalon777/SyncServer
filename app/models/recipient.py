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


class Recipient(Base):
    __tablename__ = "recipients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipient_type: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="person",
        server_default="person",
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    personnel_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    merged_into_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("recipients.id"),
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

    merged_into: Mapped["Recipient | None"] = relationship(
        "Recipient",
        remote_side=[id],
        foreign_keys=[merged_into_id],
    )

    aliases: Mapped[list["RecipientAlias"]] = relationship(
        "RecipientAlias",
        back_populates="recipient",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "recipient_type IN ('person', 'group', 'department', 'contractor', 'system_repo')",
            name="ck_recipients_type",
        ),
        Index("ix_recipients_display_name", "display_name"),
        Index("ix_recipients_personnel_no", "personnel_no"),
        Index("ix_recipients_deleted_at", "deleted_at"),
    )


class RecipientAlias(Base):
    __tablename__ = "recipient_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipient_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("recipients.id"),
        nullable=False,
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    recipient: Mapped[Recipient] = relationship("Recipient", back_populates="aliases")

    __table_args__ = (
        Index("ix_recipient_aliases_recipient_id", "recipient_id"),
    )
