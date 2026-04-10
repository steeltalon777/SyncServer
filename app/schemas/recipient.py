from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ORMBaseModel


class RecipientCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    recipient_type: str = Field(default="person", max_length=24)
    personnel_no: str | None = Field(default=None, max_length=64)


class RecipientUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    recipient_type: str | None = Field(default=None, max_length=24)
    personnel_no: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None


class RecipientMerge(BaseModel):
    source_id: int
    target_id: int


class RecipientResponse(ORMBaseModel):
    id: int
    recipient_type: str
    display_name: str
    normalized_key: str
    personnel_no: str | None = None
    is_active: bool
    merged_into_id: int | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    deleted_by_user_id: UUID | None = None


class RecipientListResponse(ORMBaseModel):
    items: list[RecipientResponse]
    total_count: int
    page: int
    page_size: int


class RecipientFilter(BaseModel):
    search: str | None = None
    recipient_type: str | None = None
    is_active: bool | None = None
    include_deleted: bool = False

    model_config = ConfigDict(extra="forbid")
