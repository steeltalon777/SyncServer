from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import INET, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    site_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("sites.id"), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    registration_token: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    last_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    client_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    site: Mapped[Site] = relationship(back_populates="devices")

    __table_args__ = (
        UniqueConstraint("site_id", "registration_token", name="uq_devices_site_registration_token"),
        Index("ix_devices_site_id", "site_id"),
        Index("ix_devices_last_seen_at", "last_seen_at"),
    )
