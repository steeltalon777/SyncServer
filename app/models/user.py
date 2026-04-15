from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    username: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_token: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        unique=True,
        default=uuid4,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )

    # Access control fields
    is_root: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="Global root flag – if true, user has unrestricted access"
    )
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Domain role: 'root', 'chief_storekeeper', 'storekeeper', 'observer'"
    )
    default_site_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("sites.id"),
        nullable=True,
        comment="Preferred working site for UI (does not restrict access)"
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

    # Relationships
    default_site: Mapped["Site | None"] = relationship("Site", foreign_keys=[default_site_id])
    access_scopes: Mapped[list["UserAccessScope"]] = relationship(
        "UserAccessScope",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="created_by_user",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ux_users_username", "username", unique=True),
        Index("ux_users_email", "email", unique=True),
        Index("ux_users_user_token", "user_token", unique=True),
        Index("ix_users_default_site_id", "default_site_id"),  # новый индекс
        CheckConstraint(
            "role IN ('root', 'chief_storekeeper', 'storekeeper', 'observer')",
            name="ck_users_role"
        ),
    )