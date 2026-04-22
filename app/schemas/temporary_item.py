from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMBaseModel


class TemporaryItemInlineCreate(BaseModel):
    client_key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    sku: str | None = Field(default=None, max_length=100)
    unit_id: int
    category_id: int | None = None
    description: str | None = Field(default=None, max_length=2000)
    hashtags: list[str] | None = None


class TemporaryItemResponse(ORMBaseModel):
    id: int
    item_id: int
    name: str
    normalized_name: str
    sku: str | None = None
    unit_id: int
    unit_name: str | None = None
    unit_symbol: str | None = None
    category_id: int
    category_name: str | None = None
    description: str | None = None
    hashtags: list[str] | None = None
    status: str
    resolution_note: str | None = None
    resolved_item_id: int | None = None
    resolution_type: str | None = None
    created_by_user_id: UUID
    resolved_by_user_id: UUID | None = None
    created_at: datetime
    resolved_at: datetime | None = None
    updated_at: datetime
    backing_item_is_active: bool | None = None


class TemporaryItemListResponse(ORMBaseModel):
    items: list[TemporaryItemResponse]
    total_count: int
    page: int
    page_size: int


class TemporaryItemMergeRequest(BaseModel):
    target_item_id: int
    comment: str | None = Field(default=None, max_length=1000)
