from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.schemas.common import ORMBaseModel


UserRole = Literal["root", "chief_storekeeper", "storekeeper", "observer"]


# Site schemas
class SiteCreate(BaseModel):
    """Schema for creating a site."""

    code: str = Field(min_length=1, max_length=64, description="Site code")
    name: str = Field(min_length=1, max_length=255, description="Site name")
    is_active: bool = Field(default=True, description="Whether the site is active")
    description: str | None = Field(default=None, max_length=500, description="Optional description")


class SiteUpdate(BaseModel):
    """Schema for updating a site."""

    code: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None
    description: str | None = Field(default=None, max_length=500)


class SiteResponse(ORMBaseModel):
    """Schema for site response (new model: int site_id)."""

    site_id: int = Field(validation_alias=AliasChoices("site_id", "id"))
    code: str
    name: str
    is_active: bool
    description: str | None = None
    created_at: datetime
    updated_at: datetime


# Device schemas
class DeviceCreate(BaseModel):
    """Schema for creating a device."""

    device_code: str | None = Field(default=None, max_length=100)
    device_name: str = Field(min_length=1, max_length=255)
    site_id: int | None = Field(default=None, description="Nullable if device is not bound to site")
    is_active: bool = True


class DeviceUpdate(BaseModel):
    """Schema for updating a device."""

    device_code: str | None = Field(default=None, max_length=100)
    device_name: str | None = Field(default=None, min_length=1, max_length=255)
    site_id: int | None = None
    is_active: bool | None = None


class DeviceResponse(ORMBaseModel):
    """Schema for device response."""

    device_id: int = Field(validation_alias=AliasChoices("device_id", "id"))
    device_code: str
    device_name: str = Field(validation_alias=AliasChoices("device_name", "name"))
    site_id: int | None = None
    is_active: bool
    last_seen_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DeviceTokenResponse(BaseModel):
    """
    Token output schema.
    Use this schema for explicit token read/rotation endpoints only.
    """

    device_id: int
    device_token: UUID = Field(validation_alias=AliasChoices("device_token", "registration_token"))
    generated_at: datetime


class UserTokenResponse(BaseModel):
    """Token output schema for explicit user token read/rotation endpoints."""

    user_id: UUID
    username: str
    user_token: UUID
    generated_at: datetime


# User schemas (new model)
class UserCreate(BaseModel):
    id: UUID | None = None
    username: str = Field(min_length=1, max_length=150)
    email: str | None = Field(default=None, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool = True
    is_root: bool = False
    role: UserRole = "observer"
    default_site_id: int | None = None


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=150)
    email: str | None = Field(default=None, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    is_root: bool | None = None
    role: UserRole | None = None
    default_site_id: int | None = None


class UserResponse(ORMBaseModel):
    id: UUID = Field(validation_alias=AliasChoices("id", "user_id"))
    username: str
    email: str | None
    full_name: str | None
    is_active: bool
    is_root: bool = False
    role: UserRole = "observer"
    default_site_id: int | None = None
    created_at: datetime
    updated_at: datetime


class UserWithTokenResponse(UserResponse):
    user_token: UUID


# User access scope schemas (new model)
class UserAccessScopeCreate(BaseModel):
    user_id: UUID
    site_id: int
    can_view: bool = True
    can_operate: bool = False
    can_manage_catalog: bool = False
    is_active: bool = True


class UserAccessScopeUpdate(BaseModel):
    can_view: bool | None = None
    can_operate: bool | None = None
    can_manage_catalog: bool | None = None
    is_active: bool | None = None


class UserAccessScopeResponse(ORMBaseModel):
    id: int
    user_id: UUID
    site_id: int
    can_view: bool
    can_operate: bool
    can_manage_catalog: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserAccessScopeReplaceItem(BaseModel):
    site_id: int
    can_view: bool = True
    can_operate: bool = False
    can_manage_catalog: bool = False


class UserAccessScopeReplaceRequest(BaseModel):
    scopes: list[UserAccessScopeReplaceItem]


class UserSyncStateResponse(BaseModel):
    user: UserWithTokenResponse
    scopes: list[UserAccessScopeResponse]


# Alias names kept for stable route payloads
class UserSiteAccessCreate(UserAccessScopeCreate):
    pass


class UserSiteAccessUpdate(UserAccessScopeUpdate):
    pass


class UserSiteAccessResponse(UserAccessScopeResponse):
    pass


# List response schemas
class SiteListResponse(ORMBaseModel):
    sites: list[SiteResponse]
    total_count: int
    page: int
    page_size: int


class DeviceListResponse(ORMBaseModel):
    devices: list[DeviceResponse]
    total_count: int
    page: int
    page_size: int


class UserListResponse(ORMBaseModel):
    users: list[UserResponse]
    total_count: int
    page: int
    page_size: int


class UserSiteAccessListResponse(ORMBaseModel):
    access_entries: list[UserSiteAccessResponse]
    total_count: int
    page: int
    page_size: int


# Filters
class SiteFilter(BaseModel):
    is_active: bool | None = None
    search: str | None = None

    model_config = ConfigDict(extra="forbid")


class DeviceFilter(BaseModel):
    site_id: int | None = None
    is_active: bool | None = None
    search: str | None = None

    model_config = ConfigDict(extra="forbid")


class UserFilter(BaseModel):
    is_active: bool | None = None
    is_root: bool | None = None
    role: UserRole | None = None
    search: str | None = None

    model_config = ConfigDict(extra="forbid")


class UserAccessScopeFilter(BaseModel):
    user_id: UUID | None = None
    site_id: int | None = None
    is_active: bool | None = None

    model_config = ConfigDict(extra="forbid")


class UserSiteAccessFilter(UserAccessScopeFilter):
    pass
