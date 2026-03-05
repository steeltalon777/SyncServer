from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Balance(Base):
    __tablename__ = "balances"

    site_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("sites.id"), primary_key=True)
    item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("items.id"), primary_key=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
