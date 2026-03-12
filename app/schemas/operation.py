from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import ORMBaseModel


# Request schemas
class OperationLineCreate(BaseModel):
    """Schema for creating an operation line."""
    
    line_number: int = Field(ge=1, description="Line number within operation")
    item_id: int = Field(ge=1, description="Item ID")
    quantity: int = Field(ge=1, description="Positive quantity")
    source_site_id: UUID | None = Field(None, description="Source site ID for MOVE operations")
    target_site_id: UUID | None = Field(None, description="Target site ID for MOVE operations")
    notes: str | None = Field(None, max_length=500, description="Line notes")


class OperationCreate(BaseModel):
    """Schema for creating an operation."""
    
    type: Literal["RECEIVE", "WRITE_OFF", "MOVE", "ISSUE"] = Field(description="Operation type")
    site_id: UUID = Field(description="Primary site ID for the operation")
    lines: list[OperationLineCreate] = Field(min_length=1, description="Operation lines")
    notes: str | None = Field(None, max_length=1000, description="Operation notes")
    
    @field_validator("lines")
    @classmethod
    def validate_lines_for_type(cls, lines: list[OperationLineCreate], info):
        """Validate lines based on operation type."""
        if info.data.get("type") == "MOVE":
            for line in lines:
                if not line.source_site_id or not line.target_site_id:
                    raise ValueError("MOVE operations require both source_site_id and target_site_id")
                if line.source_site_id == line.target_site_id:
                    raise ValueError("Source and target sites cannot be the same for MOVE operations")
        return lines


class OperationUpdate(BaseModel):
    """Schema for updating an operation."""
    
    notes: str | None = Field(None, max_length=1000, description="Operation notes")
    lines: list[OperationLineCreate] | None = Field(None, description="Updated operation lines")


class OperationSubmit(BaseModel):
    """Schema for submitting an operation."""
    
    submit: bool = Field(True, description="Submit the operation")


class OperationCancel(BaseModel):
    """Schema for cancelling an operation."""
    
    cancel: bool = Field(True, description="Cancel the operation")
    reason: str | None = Field(None, max_length=500, description="Cancellation reason")


# Response schemas
class OperationLineResponse(ORMBaseModel):
    """Schema for operation line response."""
    
    id: int
    line_number: int
    item_id: int
    quantity: int
    source_site_id: UUID | None
    target_site_id: UUID | None
    notes: str | None


class OperationResponse(ORMBaseModel):
    """Schema for operation response."""
    
    id: int
    operation_uuid: UUID
    site_id: UUID
    type: Literal["RECEIVE", "WRITE_OFF", "MOVE", "ISSUE"]
    status: Literal["draft", "submitted", "cancelled"]
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    submitted_by_user_id: int | None
    cancelled_at: datetime | None
    cancelled_by_user_id: int | None
    notes: str | None
    lines: list[OperationLineResponse]


class OperationListResponse(ORMBaseModel):
    """Schema for operation list response."""
    
    operations: list[OperationResponse]
    total_count: int
    page: int
    page_size: int


# Filter schemas
class OperationFilter(BaseModel):
    """Schema for filtering operations."""
    
    site_id: UUID | None = None
    type: Literal["RECEIVE", "WRITE_OFF", "MOVE", "ISSUE"] | None = None
    status: Literal["draft", "submitted", "cancelled"] | None = None
    created_by_user_id: int | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    updated_after: datetime | None = None
    updated_before: datetime | None = None
    search: str | None = None
    
    model_config = ConfigDict(extra="forbid")