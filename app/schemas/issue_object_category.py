from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMBaseModel


class IssueObjectCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: int | None = None
    sort_order: int = 0
    is_active: bool = True


class IssueObjectCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: int | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class IssueObjectCategoryResponse(ORMBaseModel):
    id: int
    name: str
    normalized_key: str
    parent_id: int | None = None
    sort_order: int = 0
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    deleted_by_user_id: UUID | None = None


class IssueObjectCategoryListResponse(ORMBaseModel):
    items: list[IssueObjectCategoryResponse]
    total_count: int
    page: int
    page_size: int


class TreeResponse(ORMBaseModel):
    id: int
    type: str = Field(description="'category' or 'object'")
    name: str
    comment: str | None = None
    category_id: int | None = None
    parent_id: int | None = None
    is_active: bool = True
    children: list[TreeResponse] = Field(default_factory=list)
