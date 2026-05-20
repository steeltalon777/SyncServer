from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMBaseModel


class ReviewItemResponse(ORMBaseModel):
    """Response model for catalog items that require review."""

    id: int
    item_name: str
    sku: str | None = None
    category_id: int
    category_name: str | None = None
    unit_id: int
    unit_name: str | None = None
    unit_symbol: str | None = None
    description: str | None = None
    hashtags: list[str] | None = None
    is_active: bool
    requires_review: bool = True
    review_status: str | None = None
    review_created_by_user_id: UUID | None = None
    review_resolved_by_user_id: UUID | None = None
    review_resolved_at: datetime | None = None
    review_note: str | None = None
    created_at: datetime
    updated_at: datetime


class ReviewItemListResponse(ORMBaseModel):
    items: list[ReviewItemResponse]
    total_count: int
    page: int
    page_size: int


class ReviewItemDetailResponse(ORMBaseModel):
    """Extended detail for a review-required item including balances and operations."""

    id: int
    item_name: str
    sku: str | None = None
    category_id: int
    category_name: str | None = None
    unit_id: int
    unit_name: str | None = None
    unit_symbol: str | None = None
    description: str | None = None
    hashtags: list[str] | None = None
    is_active: bool
    requires_review: bool = True
    review_status: str | None = None
    review_created_by_user_id: UUID | None = None
    review_resolved_by_user_id: UUID | None = None
    review_resolved_at: datetime | None = None
    review_note: str | None = None
    created_at: datetime
    updated_at: datetime
    balances_per_site: list[ReviewItemBalanceDto] = Field(default_factory=list)
    operations_count: int = 0


class ReviewItemBalanceDto(ORMBaseModel):
    site_id: int
    site_name: str | None = None
    qty: int = 0


class ReviewItemMergeRequest(BaseModel):
    target_item_id: int
    comment: str | None = Field(default=None, max_length=1000)


class ReviewItemConfirmRequest(BaseModel):
    """Payload for confirming a review item. Validates required catalog fields."""

    name: str | None = None
    sku: str | None = None
    category_id: int | None = None
    unit_id: int | None = None
    description: str | None = None
    hashtags: list[str] | None = None
