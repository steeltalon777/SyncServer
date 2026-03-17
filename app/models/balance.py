from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Balance(Base):
    __tablename__ = "balances"

    site_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sites.id"),
        primary_key=True,
    )
    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id"),
        primary_key=True,
    )
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )