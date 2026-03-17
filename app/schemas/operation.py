from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import ORMBaseModel


OperationType = Literal[
    "RECEIVE",
    "WRITE_OFF",
    "MOVE",
]
OperationStatus = Literal["draft", "submitted", "cancelled"]


class OperationLineCreate(BaseModel):
    """Operation line input aligned to current model."""

    line_number: int = Field(ge=1)
    item_id: int
    qty: int = Field(ge=1, validation_alias=AliasChoices("qty", "quantity"))
    batch: str | None = None
    comment: str | None = None

    @property
    def quantity(self) -> int:
        return self.qty

    @property
    def notes(self) -> str | None:
        return self.comment


class OperationCreate(BaseModel):
    """Operation create payload aligned to agreed model."""

    operation_type: OperationType = Field(validation_alias=AliasChoices("operation_type", "type"))
    site_id: int
    source_site_id: int | None = None
    destination_site_id: int | None = Field(default=None, validation_alias=AliasChoices("destination_site_id", "target_site_id"))
    issued_to_user_id: UUID | None = None
    issued_to_name: str | None = Field(default=None, max_length=255)
    lines: list[OperationLineCreate] = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=1000)

    @property
    def type(self) -> OperationType:
        return self.operation_type

    @field_validator("lines")
    @classmethod
    def validate_lines_for_type(cls, lines: list[OperationLineCreate], info):
        operation_type = info.data.get("operation_type")
        if operation_type == "MOVE":
            src = info.data.get("source_site_id")
            dst = info.data.get("destination_site_id")
            if not src or not dst:
                raise ValueError("MOVE operations require source and destination site ids")
            if src == dst:
                raise ValueError("Source and destination sites must differ")
        return lines


class OperationUpdate(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)
    source_site_id: int | None = None
    destination_site_id: int | None = Field(default=None, validation_alias=AliasChoices("destination_site_id", "target_site_id"))
    issued_to_user_id: UUID | None = None
    issued_to_name: str | None = Field(default=None, max_length=255)
    lines: list[OperationLineCreate] | None = None


class OperationSubmit(BaseModel):
    submit: bool = True


class OperationCancel(BaseModel):
    cancel: bool = True
    reason: str | None = Field(default=None, max_length=500)


class OperationLineResponse(ORMBaseModel):
    id: int
    line_number: int
    item_id: int
    qty: int = Field(validation_alias=AliasChoices("qty", "quantity"))
    batch: str | None = None
    comment: str | None = Field(default=None, validation_alias=AliasChoices("comment", "notes"))

    @property
    def quantity(self) -> int:
        return self.qty

    @property
    def notes(self) -> str | None:
        return self.comment


class OperationResponse(ORMBaseModel):
    id: UUID = Field(validation_alias=AliasChoices("id", "operation_uuid"))
    site_id: int
    operation_type: OperationType = Field(validation_alias=AliasChoices("operation_type", "type"))
    status: OperationStatus
    source_site_id: int | None = None
    destination_site_id: int | None = Field(default=None, validation_alias=AliasChoices("destination_site_id", "target_site_id"))
    issued_to_user_id: UUID | None = None
    issued_to_name: str | None = None
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None = None
    submitted_by_user_id: UUID | None = None
    cancelled_at: datetime | None = None
    cancelled_by_user_id: UUID | None = None
    notes: str | None = None
    lines: list[OperationLineResponse] = Field(default_factory=list)

    @property
    def type(self) -> OperationType:
        return self.operation_type


class OperationListResponse(ORMBaseModel):
    items: list[OperationResponse]
    total_count: int
    page: int
    page_size: int


class OperationFilter(BaseModel):
    site_id: int | None = None
    operation_type: OperationType | None = Field(default=None, validation_alias=AliasChoices("operation_type", "type"))
    status: OperationStatus | None = None
    created_by_user_id: UUID | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    updated_after: datetime | None = None
    updated_before: datetime | None = None
    search: str | None = None

    model_config = ConfigDict(extra="forbid")

    @property
    def type(self) -> OperationType | None:
        return self.operation_type
