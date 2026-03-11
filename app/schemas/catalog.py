from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMBaseModel


class CatalogRequest(BaseModel):
    updated_after: datetime | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class CategoryDto(ORMBaseModel):
    id: UUID
    name: str
    parent_id: UUID | None = None
    is_active: bool
    updated_at: datetime


class ItemDto(ORMBaseModel):
    id: UUID
    sku: str | None = None
    name: str
    category_id: UUID
    unit_id: UUID
    description: str | None = None
    is_active: bool
    updated_at: datetime


class UnitDto(ORMBaseModel):
    id: UUID
    name: str
    symbol: str
    is_active: bool
    updated_at: datetime


class CatalogItemsResponse(ORMBaseModel):
    items: list[ItemDto]
    server_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    next_updated_after: datetime | None = None


class CatalogCategoriesResponse(ORMBaseModel):
    categories: list[CategoryDto]
    server_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    next_updated_after: datetime | None = None


class CatalogUnitsResponse(ORMBaseModel):
    units: list[UnitDto]
    server_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    next_updated_after: datetime | None = None


class CategoryTreeNode(ORMBaseModel):
    id: UUID
    name: str
    code: str | None = None
    parent_id: UUID | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    sort_order: int | None = None
    path: list[str] = Field(default_factory=list)
    children: list["CategoryTreeNode"] = Field(default_factory=list)


class UnitCreateRequest(BaseModel):
    id: UUID | None = None
    name: str = Field(min_length=1, max_length=100)
    symbol: str = Field(min_length=1, max_length=20)
    sort_order: int | None = None
    is_active: bool = True


class UnitUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    symbol: str | None = Field(default=None, min_length=1, max_length=20)
    sort_order: int | None = None
    is_active: bool | None = None


class UnitResponse(ORMBaseModel):
    id: UUID
    name: str
    symbol: str
    sort_order: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CategoryCreateRequest(BaseModel):
    id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=100)
    parent_id: UUID | None = None
    sort_order: int | None = None
    is_active: bool = True


class CategoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=100)
    parent_id: UUID | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class CategoryResponse(ORMBaseModel):
    id: UUID
    name: str
    code: str | None = None
    parent_id: UUID | None = None
    sort_order: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ItemCreateRequest(BaseModel):
    id: UUID | None = None
    sku: str | None = Field(default=None, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    category_id: UUID
    unit_id: UUID
    description: str | None = None
    is_active: bool = True


class ItemUpdateRequest(BaseModel):
    sku: str | None = Field(default=None, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category_id: UUID | None = None
    unit_id: UUID | None = None
    description: str | None = None
    is_active: bool | None = None


class ItemResponse(ORMBaseModel):
    id: UUID
    sku: str | None = None
    name: str
    category_id: UUID
    unit_id: UUID
    description: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


CategoryTreeNode.model_rebuild()
