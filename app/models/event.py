from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Site, Device
from app.models.base import Base


class Event(Base):
    __tablename__ = "events"

    event_uuid: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    site_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("sites.id"), nullable=False)
    device_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("devices.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    server_seq: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False, unique=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    site: Mapped[Site] = relationship()
    device: Mapped[Device | None] = relationship()

    __table_args__ = (
        Index("ix_events_site_id_server_seq", "site_id", "server_seq"),
        Index("ix_events_site_id_event_datetime", "site_id", "event_datetime"),
        Index("ix_events_event_type", "event_type"),
    )
