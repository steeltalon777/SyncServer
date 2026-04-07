from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMBaseModel


class CatalogRequest(BaseModel):
    updated_after: datetime | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class CategoryDto(ORMBaseModel):
    id: int
    name: str
    parent_id: int | None = None
    is_active: bool
    updated_at: datetime


class ItemDto(ORMBaseModel):
    id: int
    sku: str | None = None
    name: str
    category_id: int
    unit_id: int
    description: str | None = None
    is_active: bool
    hashtags: list[str] | None = None
    updated_at: datetime


class UnitDto(ORMBaseModel):
    id: int
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


class CategorySummaryDto(ORMBaseModel):
    id: int
    name: str


class ItemPreviewDto(ORMBaseModel):
    id: int
    name: str


class CatalogBrowseCategoryDto(ORMBaseModel):
    id: int
    name: str
    code: str | None = None
    parent_id: int | None = None
    parent: CategorySummaryDto | None = None
    parent_chain_summary: list[CategorySummaryDto] = Field(default_factory=list)
    children_count: int = 0
    items_count: int = 0
    items_preview: list[ItemPreviewDto] = Field(default_factory=list)
    is_active: bool
    updated_at: datetime
    sort_order: int | None = None


class CatalogBrowseCategoriesResponse(ORMBaseModel):
    categories: list[CatalogBrowseCategoryDto]
    total_count: int
    page: int
    page_size: int


class CatalogBrowseItemDto(ORMBaseModel):
    id: int
    sku: str | None = None
    name: str
    category_id: int
    category_name: str
    unit_id: int
    unit_symbol: str
    description: str | None = None
    is_active: bool
    updated_at: datetime


class CatalogBrowseItemsResponse(ORMBaseModel):
    items: list[CatalogBrowseItemDto]
    total_count: int
    page: int
    page_size: int


class CategoryParentChainResponse(ORMBaseModel):
    category_id: int
    parent_chain_summary: list[CategorySummaryDto] = Field(default_factory=list)


class CategoryTreeNode(ORMBaseModel):
    id: int
    name: str
    code: str | None = None
    parent_id: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    sort_order: int | None = None
    path: list[str] = Field(default_factory=list)
    children: list["CategoryTreeNode"] = Field(default_factory=list)


class UnitCreateRequest(BaseModel):
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
    id: int
    name: str
    symbol: str
    sort_order: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=100)
    parent_id: int | None = None
    sort_order: int | None = None
    is_active: bool = True


class CategoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=100)
    parent_id: int | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class CategoryResponse(ORMBaseModel):
    id: int
    name: str
    code: str | None = None
    parent_id: int | None = None
    sort_order: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ItemCreateRequest(BaseModel):
    sku: str | None = Field(default=None, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    category_id: int | None = None
    unit_id: int
    description: str | None = None
    hashtags: list[str] | None = None
    is_active: bool = True

    @field_validator("category_id", mode="before")
    @classmethod
    def normalize_category_id(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value


class ItemUpdateRequest(BaseModel):
    sku: str | None = Field(default=None, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category_id: int | None = None
    unit_id: int | None = None
    description: str | None = None
    hashtags: list[str] | None = None
    is_active: bool | None = None

    @field_validator("category_id", mode="before")
    @classmethod
    def normalize_category_id(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value


class ItemResponse(ORMBaseModel):
    id: int
    sku: str | None = None
    name: str
    category_id: int
    unit_id: int
    description: str | None = None
    is_active: bool
    hashtags: list[str] | None = None
    created_at: datetime
    updated_at: datetime


class CatalogSiteDto(ORMBaseModel):
    site_id: int
    code: str
    name: str
    is_active: bool
    permissions: dict[str, bool]


class CatalogSitesResponse(ORMBaseModel):
    sites: list[CatalogSiteDto]
    server_time: datetime = Field(default_factory=lambda: datetime.now(UTC))


CategoryTreeNode.model_rebuild()
