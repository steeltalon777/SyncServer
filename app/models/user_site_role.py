# app/models/user_site_role.py
# DEPRECATED: This model is legacy and will be removed in future versions.
# DO NOT USE IN NEW CODE.
# TYPE MISMATCH WITH NEW MODEL:
#   - user_id is INTEGER (BigInteger) but new User.id is UUID
#   - site_id is UUID but new Site.id is INTEGER
# Use UserAccessScope for per-site permissions instead.

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserSiteRole(Base):
    __tablename__ = "user_site_roles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    site_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sites.id"),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(String(32), nullable=False)

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
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

    __table_args__ = (
        UniqueConstraint("user_id", "site_id", name="uq_user_site_roles_user_site"),
        CheckConstraint(
            "role IN ('root','chief_storekeeper','storekeeper','observer')",
            name="ck_user_site_roles_role",
        ),
    )