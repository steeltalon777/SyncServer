from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMBaseModel


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


class CatalogItemsResponse(ORMBaseModel):
    items: list[ItemDto]
    server_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    next_updated_after: datetime | None = None


class CatalogCategoriesResponse(ORMBaseModel):
    categories: list[CategoryDto]
    server_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    next_updated_after: datetime | None = None


class CatalogRequest(BaseModel):
    updated_after: datetime | None = None
    limit: int = Field(default=100, ge=1, le=1000)


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

class CatalogUnitsResponse(BaseModel):
    units: list[UnitDto]
    server_time: datetime

class UnitDto(ORMBaseModel):
    id: UUID
    name: str
    symbol: str
    is_active: bool
    updated_at: datetime


class CatalogUnitsResponse(ORMBaseModel):
    units: list[UnitDto]
    server_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    next_updated_after: datetime | None = None
CategoryTreeNode.model_rebuild()