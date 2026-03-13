from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import ORMBaseModel


# Site schemas
class SiteCreate(BaseModel):
    """Schema for creating a site."""
    
    name: str = Field(min_length=1, max_length=100, description="Site name")
    code: str = Field(min_length=1, max_length=20, description="Site code")
    description: str | None = Field(None, max_length=500, description="Site description")
    is_active: bool = Field(default=True, description="Whether the site is active")


class SiteUpdate(BaseModel):
    """Schema for updating a site."""
    
    name: str | None = Field(None, min_length=1, max_length=100, description="Site name")
    code: str | None = Field(None, min_length=1, max_length=20, description="Site code")
    description: str | None = Field(None, max_length=500, description="Site description")
    is_active: bool | None = Field(None, description="Whether the site is active")


class SiteResponse(ORMBaseModel):
    """Schema for site response."""
    
    id: UUID
    name: str
    code: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# Device schemas
class DeviceCreate(BaseModel):
    """Schema for creating a device."""
    
    site_id: UUID = Field(description="Site ID the device belongs to")
    name: str = Field(min_length=1, max_length=100, description="Device name")
    description: str | None = Field(None, max_length=500, description="Device description")


class DeviceUpdate(BaseModel):
    """Schema for updating a device."""
    
    name: str | None = Field(None, min_length=1, max_length=100, description="Device name")
    description: str | None = Field(None, max_length=500, description="Device description")
    is_active: bool | None = Field(None, description="Whether the device is active")


class DeviceResponse(ORMBaseModel):
    """Schema for device response."""
    
    id: UUID
    site_id: UUID
    name: str
    description: str | None
    is_active: bool
    registration_token: UUID
    last_seen_at: datetime | None
    last_seen_ip: str | None
    last_seen_client_version: str | None
    created_at: datetime
    updated_at: datetime


class DeviceTokenResponse(BaseModel):
    """Schema for device token response (used for token rotation)."""
    
    device_id: UUID
    registration_token: UUID
    generated_at: datetime


# User and access schemas
class UserCreate(BaseModel):
    """Schema for creating a user."""
    
    user_id: int = Field(ge=1, description="User ID (external system ID)")
    username: str = Field(min_length=1, max_length=100, description="Username")
    email: str | None = Field(None, max_length=255, description="Email address")
    full_name: str | None = Field(None, max_length=200, description="Full name")
    is_active: bool = Field(default=True, description="Whether the user is active")


class UserUpdate(BaseModel):
    """Schema for updating a user."""
    
    username: str | None = Field(None, min_length=1, max_length=100, description="Username")
    email: str | None = Field(None, max_length=255, description="Email address")
    full_name: str | None = Field(None, max_length=200, description="Full name")
    is_active: bool | None = Field(None, description="Whether the user is active")


class UserResponse(ORMBaseModel):
    """Schema for user response."""
    
    user_id: int
    username: str
    email: str | None
    full_name: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserSiteAccessCreate(BaseModel):
    """Schema for creating user-site access."""
    
    user_id: int = Field(ge=1, description="User ID")
    site_id: UUID = Field(description="Site ID")
    role: Literal["root", "chief_storekeeper", "storekeeper", "observer"] = Field(description="User role for this site")


class UserSiteAccessUpdate(BaseModel):
    """Schema for updating user-site access."""
    
    role: Literal["root", "chief_storekeeper", "storekeeper", "observer"] | None = Field(None, description="User role for this site")
    is_active: bool | None = Field(None, description="Whether the access is active")


class UserSiteAccessResponse(ORMBaseModel):
    """Schema for user-site access response."""
    
    id: int
    user_id: int
    site_id: UUID
    role: Literal["root", "chief_storekeeper", "storekeeper", "observer"]
    is_active: bool
    created_at: datetime
    updated_at: datetime


# List response schemas
class SiteListResponse(ORMBaseModel):
    """Schema for site list response."""
    
    sites: list[SiteResponse]
    total_count: int
    page: int
    page_size: int


class DeviceListResponse(ORMBaseModel):
    """Schema for device list response."""
    
    devices: list[DeviceResponse]
    total_count: int
    page: int
    page_size: int


class UserListResponse(ORMBaseModel):
    """Schema for user list response."""
    
    users: list[UserResponse]
    total_count: int
    page: int
    page_size: int


class UserSiteAccessListResponse(ORMBaseModel):
    """Schema for user-site access list response."""
    
    access_entries: list[UserSiteAccessResponse]
    total_count: int
    page: int
    page_size: int


# Filter schemas
class SiteFilter(BaseModel):
    """Schema for filtering sites."""
    
    is_active: bool | None = None
    search: str | None = None
    
    model_config = ConfigDict(extra="forbid")


class DeviceFilter(BaseModel):
    """Schema for filtering devices."""
    
    site_id: UUID | None = None
    is_active: bool | None = None
    search: str | None = None
    
    model_config = ConfigDict(extra="forbid")


class UserFilter(BaseModel):
    """Schema for filtering users."""
    
    is_active: bool | None = None
    search: str | None = None
    
    model_config = ConfigDict(extra="forbid")


class UserSiteAccessFilter(BaseModel):
    """Schema for filtering user-site access."""
    
    user_id: int | None = None
    site_id: UUID | None = None
    role: Literal["root", "chief_storekeeper", "storekeeper", "observer"] | None
    is_active: bool | None = None
    
    model_config = ConfigDict(extra="forbid")