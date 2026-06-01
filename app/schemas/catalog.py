from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.schemas.common import ORMBaseModel
from pydantic import BaseModel, Field, field_validator


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
    requires_review: bool = False
    review_status: str | None = None
    review_created_by_user_id: UUID | None = None
    review_resolved_by_user_id: UUID | None = None
    review_resolved_at: datetime | None = None
    review_note: str | None = None
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
    requires_review: bool = False
    review_status: str | None = None
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


class UnitBulkCreateRequest(BaseModel):
    items: list[UnitCreateRequest] = Field(min_length=1)


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
    deleted_at: datetime | None = None
    deleted_by_user_id: UUID | None = None
    created_by_user_id: UUID | None = None
    updated_by_user_id: UUID | None = None


class UnitBulkCreateResponse(ORMBaseModel):
    items: list[UnitResponse]


class CategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=100)
    parent_id: int | None = None
    sort_order: int | None = None
    is_active: bool = True


class CategoryBulkCreateRequest(BaseModel):
    items: list[CategoryCreateRequest] = Field(min_length=1)


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
    deleted_at: datetime | None = None
    deleted_by_user_id: UUID | None = None
    created_by_user_id: UUID | None = None
    updated_by_user_id: UUID | None = None


class CategoryBulkCreateResponse(ORMBaseModel):
    items: list[CategoryResponse]


class ItemCreateRequest(BaseModel):
    sku: str | None = Field(default=None, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    category_id: int | None = None
    unit_id: int
    description: str | None = None
    hashtags: list[str] | None = None
    is_active: bool = True
    requires_review: bool = False

    @field_validator("sku", "description", "category_id", mode="before")
    @classmethod
    def normalize_blank_strings(cls, value: object) -> object:
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

    @field_validator("sku", "description", "category_id", mode="before")
    @classmethod
    def normalize_blank_strings(cls, value: object) -> object:
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
    requires_review: bool = False
    review_status: str | None = None
    review_created_by_user_id: UUID | None = None
    review_resolved_by_user_id: UUID | None = None
    review_resolved_at: datetime | None = None
    review_note: str | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    deleted_by_user_id: UUID | None = None
    created_by_user_id: UUID | None = None
    updated_by_user_id: UUID | None = None


class CatalogSiteDto(ORMBaseModel):
    site_id: int
    code: str
    name: str
    is_active: bool
    permissions: dict[str, bool]


class CatalogSitesResponse(ORMBaseModel):
    sites: list[CatalogSiteDto]
    server_time: datetime = Field(default_factory=lambda: datetime.now(UTC))


class UnitFilter(BaseModel):
    """Фильтры для списка единиц измерения."""
    search: str | None = None
    is_active: bool | None = None
    include_deleted: bool = False


class CategoryFilter(BaseModel):
    """Фильтры для списка категорий."""
    search: str | None = None
    is_active: bool | None = None
    parent_id: int | None = None
    include_deleted: bool = False


class ItemFilter(BaseModel):
    """Фильтры для списка номенклатуры."""
    search: str | None = None
    is_active: bool | None = None
    category_id: int | None = None
    unit_id: int | None = None
    requires_review: bool | None = None
    include_deleted: bool = False


class UnitListResponse(ORMBaseModel):
    items: list[UnitResponse]
    total_count: int
    page: int
    page_size: int


class CategoryListResponse(ORMBaseModel):
    items: list[CategoryResponse]
    total_count: int
    page: int
    page_size: int


class ItemListResponse(ORMBaseModel):
    items: list[ItemResponse]
    total_count: int
    page: int
    page_size: int


# ─── Batch Catalog API Schemas ──────────────────────────────────────


class BatchChangeUnitPayload(BaseModel):
    """Payload for unit create action."""
    name: str = Field(min_length=1, max_length=100)
    symbol: str = Field(min_length=1, max_length=20)
    sort_order: int | None = None
    is_active: bool = True


class BatchChangeCategoryPayload(BaseModel):
    """Payload for category create action."""
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=100)
    parent_id: int | None = None
    parent_local_id: str | None = None
    sort_order: int | None = None
    is_active: bool = True

    def model_post_init(self, __context) -> None:
        # Ensure only one of parent_id or parent_local_id is set
        if self.parent_id is not None and self.parent_local_id is not None:
            raise ValueError("Cannot specify both parent_id and parent_local_id")


class BatchChangeItemPayload(BaseModel):
    """Payload for item create action."""
    sku: str | None = Field(default=None, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    category_id: int | None = None
    category_local_id: str | None = None
    unit_id: int | None = None
    unit_local_id: str | None = None
    description: str | None = None
    hashtags: list[str] | None = None
    is_active: bool = True
    requires_review: bool = False

    def model_post_init(self, __context) -> None:
        # Ensure only one of category_id or category_local_id is set
        if self.category_id is not None and self.category_local_id is not None:
            raise ValueError("Cannot specify both category_id and category_local_id")
        # Ensure only one of unit_id or unit_local_id is set
        if self.unit_id is not None and self.unit_local_id is not None:
            raise ValueError("Cannot specify both unit_id and unit_local_id")


class BatchChangeUpdatePayload(BaseModel):
    """Payload for update action (common fields)."""
    sku: str | None = Field(default=None, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category_id: int | None = None
    unit_id: int | None = None
    description: str | None = None
    hashtags: list[str] | None = None
    is_active: bool | None = None


class BatchChangeBase(BaseModel):
    """Base schema for a single change in the batch."""
    local_id: str = Field(min_length=1, max_length=128)
    entity_type: str  # 'unit', 'category', 'item'
    action: str  # 'create', 'update', 'deactivate', 'delete'
    entity_id: int | None = None  # Required for update/deactivate/delete


class BatchChangeCreate(BatchChangeBase):
    """Schema for create action."""
    action: str = "create"
    payload: BatchChangeUnitPayload | BatchChangeCategoryPayload | BatchChangeItemPayload

    def model_post_init(self, __context) -> None:
        if self.entity_id is not None:
            raise ValueError("entity_id is forbidden for create action")


class BatchChangeUpdate(BatchChangeBase):
    """Schema for update action."""
    action: str = "update"
    payload: BatchChangeUpdatePayload

    def model_post_init(self, __context) -> None:
        if self.entity_id is None:
            raise ValueError("entity_id is required for update action")


class BatchChangeDeactivate(BatchChangeBase):
    """Schema for deactivate action."""
    action: str = "deactivate"

    def model_post_init(self, __context) -> None:
        if self.entity_id is None:
            raise ValueError("entity_id is required for deactivate action")


class BatchChangeDelete(BatchChangeBase):
    """Schema for delete action."""
    action: str = "delete"

    def model_post_init(self, __context) -> None:
        if self.entity_id is None:
            raise ValueError("entity_id is required for delete action")


# Union type for batch changes
BatchChange = BatchChangeCreate | BatchChangeUpdate | BatchChangeDeactivate | BatchChangeDelete


class CatalogBatchRequest(BaseModel):
    """Request schema for batch catalog endpoint."""
    client_batch_id: str = Field(min_length=1, max_length=256)
    mode: str = "atomic"  # Only 'atomic' supported in this TZ
    changes: list[BatchChange] = Field(min_length=1)

    def model_post_init(self, __context) -> None:
        if self.mode != "atomic":
            raise ValueError("Only 'atomic' mode is supported")
        # Check for duplicate local_ids
        local_ids = [change.local_id for change in self.changes]
        if len(local_ids) != len(set(local_ids)):
            raise ValueError("Duplicate local_id found in batch changes")


class BatchChangeResult(BaseModel):
    """Result for a single change in the batch response."""
    local_id: str
    entity_type: str
    action: str
    status: str  # 'applied', 'error'
    entity_id: int | None = None
    error_code: str | None = None
    error_message: str | None = None


class CatalogBatchResponse(ORMBaseModel):
    """Response schema for batch catalog endpoint."""
    client_batch_id: str
    mode: str
    status: str  # 'applied', 'failed'
    summary: dict[str, int]
    records: list[BatchChangeResult]
    server_time: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CatalogBatchErrorDetail(BaseModel):
    """Error detail for batch validation error response."""
    local_id: str
    entity_type: str
    action: str
    code: str
    message: str


class CatalogBatchErrorResponse(BaseModel):
    """Error response schema for batch catalog endpoint."""
    detail: str
    errors: list[CatalogBatchErrorDetail]


CategoryTreeNode.model_rebuild()
