from __future__ import annotations

from datetime import datetime

from uuid import UUID, uuid4
from sqlalchemy import Boolean, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Text

from app.models.base import Base


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    devices = relationship("Device", back_populates="site")

    operations = relationship(
        "Operation",
        back_populates="site",
    )

    __table_args__ = (Index("ux_sites_code", "code", unique=True),)
