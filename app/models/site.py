from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Boolean, DateTime
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import List
from app.models.base import Base

class Site(Base):
    __tablename__ = "sites"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200),nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda : datetime.now(timezone.utc)
    )

    #Связь с Device
    devices : Mapped[List["Device"]] = relationship(
        back_populates="site",
        cascade="all, delete-orphan"
    )
