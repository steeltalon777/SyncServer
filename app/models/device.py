from sqlalchemy.orm import Mapped,mapped_column,relationship
from sqlalchemy import String, Boolean, DateTime, ForeignKey
from datetime import datetime, timezone
from uuid import UUID, uuid4
from app.models.base import Base

class Device(Base):
    __tablename__ = "devices"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    site_id: Mapped[UUID] = mapped_column(ForeignKey("sites.id"),nullable=False)
    name: Mapped[str | None] = mapped_column(String(100),nullable=True)
    registration_token: Mapped[UUID] = mapped_column(nullable=False)
    last_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    client_version  : Mapped[str | None] = mapped_column(String(20),nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean,default=True)
    created_at : Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda : datetime.now(timezone.utc)
    )

    # Связь с Site (для удобства)
    site: Mapped["Site"] = relationship(back_populates="devices")
    