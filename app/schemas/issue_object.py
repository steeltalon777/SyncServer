from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import ORMBaseModel


class IssueObjectCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    object_type: str = Field(default="person", max_length=24)
    code: str | None = Field(default=None, max_length=64)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_blank_strings(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value


class IssueObjectUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    object_type: str | None = Field(default=None, max_length=24)
    code: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None

    @field_validator("code", mode="before")
    @classmethod
    def normalize_blank_strings(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value


class IssueObjectMerge(BaseModel):
    source_id: int
    target_id: int


class IssueObjectResponse(ORMBaseModel):
    id: int
    display_name: str
    object_type: str
    code: str | None = None
    normalized_key: str
    is_active: bool
    merged_into_id: int | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    deleted_by_user_id: UUID | None = None


class IssueObjectListResponse(ORMBaseModel):
    items: list[IssueObjectResponse]
    total_count: int
    page: int
    page_size: int


class IssueObjectFilter(BaseModel):
    search: str | None = None
    object_type: str | None = None
    is_active: bool | None = None
    include_deleted: bool = False

    model_config = ConfigDict(extra="forbid")
