from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ORMBaseModel


class BalanceResponse(ORMBaseModel):
    """Schema for balance response."""

    site_id: UUID
    item_id: UUID
    quantity: Decimal
    updated_at: datetime


class BalanceListResponse(ORMBaseModel):
    """Schema for balance list response."""

    balances: list[BalanceResponse]
    total_count: int
    page: int
    page_size: int


class BalanceFilter(BaseModel):
    """Schema for filtering balances."""

    site_id: UUID | None = None
    item_id: UUID | None = None
    category_id: UUID | None = None
    search: str | None = None
    only_positive: bool = Field(default=False, description="Show only positive balances")

    model_config = ConfigDict(extra="forbid")