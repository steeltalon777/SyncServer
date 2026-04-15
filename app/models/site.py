from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    devices = relationship("Device", back_populates="site")

    operations = relationship(
        "Operation",
        back_populates="site",
        foreign_keys="Operation.site_id",
    )

    source_operations = relationship(
        "Operation",
        back_populates="source_site",
        foreign_keys="Operation.source_site_id",
    )

    destination_operations = relationship(
        "Operation",
        back_populates="destination_site",
        foreign_keys="Operation.destination_site_id",
    )

    access_scopes: Mapped[list["UserAccessScope"]] = relationship(
        "UserAccessScope",
        back_populates="site",
        cascade="all, delete-orphan",
    )
    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="site",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ux_sites_code", "code", unique=True),
    )