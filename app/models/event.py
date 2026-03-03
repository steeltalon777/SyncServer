from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, DateTime, ForeignKey, JSON, BigInteger, Sequence
from datetime import datetime, timezone
from uuid import UUID
from app.models.base import Base


class Event(Base):
    __tablename__ = "events"

    # Первичный ключ - UUID события (генерируется клиентом)
    event_uuid: Mapped[UUID] = mapped_column(primary_key=True)

    # Связи
    site_id: Mapped[UUID] = mapped_column(ForeignKey("sites.id"), nullable=False)
    device_id: Mapped[UUID | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(nullable=True)  # ID из Django

    # Данные события
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    schema_version: Mapped[int] = mapped_column(Integer, default=1)

    # Payload события (JSONB в PostgreSQL)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Служебные поля
    server_seq: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Связи (для удобства)
    site: Mapped["Site"] = relationship()
    device: Mapped["Device"] = relationship()