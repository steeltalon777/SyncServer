# app/models/user_access_scope.py
from __future__ import annotations
from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class UserAccessScope(Base):
    """
    Defines a user's access scope to a specific site.
    Supports per-site granular permissions without binding the user's role
    to a single site.
    """
    __tablename__ = "user_access_scopes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    site_id: Mapped[int] = mapped_column(Integer, ForeignKey("sites.id"), nullable=False)

    can_view: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    can_operate: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    can_manage_catalog: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="access_scopes")
    site: Mapped["Site"] = relationship("Site", back_populates="access_scopes")

    __table_args__ = (
        UniqueConstraint("user_id", "site_id", name="uq_user_access_scope_user_site"),
        Index("ix_user_access_scope_user_id", "user_id"),
        Index("ix_user_access_scope_site_id", "site_id"),
    )
