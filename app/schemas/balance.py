from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ORMBaseModel


# Response schemas
class BalanceResponse(ORMBaseModel):
    """Schema for balance response."""
    
    site_id: UUID
    item_id: int
    quantity: int
    updated_at: str  # ISO format string


class BalanceListResponse(ORMBaseModel):
    """Schema for balance list response."""
    
    balances: list[BalanceResponse]
    total_count: int
    page: int
    page_size: int


# Filter schemas
class BalanceFilter(BaseModel):
    """Schema for filtering balances."""
    
    site_id: UUID | None = None
    item_id: int | None = None
    category_id: int | None = None
    search: str | None = None
    only_positive: bool = Field(default=False, description="Show only positive balances")
    
    model_config = ConfigDict(extra="forbid")