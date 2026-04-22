from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from app.schemas.common import ORMBaseModel
from app.schemas.temporary_item import TemporaryItemInlineCreate


OperationType = Literal[
    "RECEIVE",
    "EXPENSE",
    "WRITE_OFF",
    "MOVE",
    "ADJUSTMENT",
    "ISSUE",
    "ISSUE_RETURN",
]
OperationStatus = Literal["draft", "submitted", "cancelled"]
AcceptanceState = Literal["not_required", "pending", "in_progress", "resolved"]


class OperationLineCreate(BaseModel):
    """Operation line input aligned to current model."""

    line_number: int = Field(ge=1)
    item_id: int | None = None
    temporary_item: TemporaryItemInlineCreate | None = None
    qty: int = Field(validation_alias=AliasChoices("qty", "quantity"))
    batch: str | None = None
    comment: str | None = None

    @property
    def quantity(self) -> int:
        return self.qty

    @property
    def notes(self) -> str | None:
        return self.comment

    @field_validator("qty")
    @classmethod
    def validate_qty_not_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("qty must not be zero")
        return value

    @model_validator(mode="after")
    def validate_item_xor_temporary(self) -> "OperationLineCreate":
        if self.item_id is None and self.temporary_item is None:
            raise ValueError("either item_id or temporary_item must be provided")
        if self.item_id is not None and self.temporary_item is not None:
            raise ValueError("item_id and temporary_item cannot be provided together")
        return self


class OperationCreate(BaseModel):
    """Operation create payload aligned to agreed model."""

    operation_type: OperationType = Field(validation_alias=AliasChoices("operation_type", "type"))
    site_id: int
    effective_at: datetime | None = None
    source_site_id: int | None = None
    destination_site_id: int | None = Field(default=None, validation_alias=AliasChoices("destination_site_id", "target_site_id"))
    issued_to_user_id: UUID | None = None
    issued_to_name: str | None = Field(default=None, max_length=255)
    recipient_id: int | None = None
    recipient_name_snapshot: str | None = Field(
        default=None,
        validation_alias=AliasChoices("recipient_name_snapshot", "recipient_name", "issued_to_name"),
        max_length=255,
    )
    lines: list[OperationLineCreate] = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=1000)
    client_request_id: str | None = Field(default=None, max_length=100)

    @property
    def type(self) -> OperationType:
        return self.operation_type

    @field_validator("lines")
    @classmethod
    def validate_lines_for_type(cls, lines: list[OperationLineCreate], info: ValidationInfo):
        operation_type = info.data.get("operation_type")
        if operation_type == "MOVE":
            src = info.data.get("source_site_id")
            dst = info.data.get("destination_site_id")
            if not src or not dst:
                raise ValueError("MOVE operations require source and destination site ids")
            if src == dst:
                raise ValueError("Source and destination sites must differ")
        if operation_type == "ADJUSTMENT":
            return lines
        if operation_type in {"ISSUE", "ISSUE_RETURN"}:
            recipient_id = info.data.get("recipient_id")
            recipient_name = info.data.get("recipient_name_snapshot") or info.data.get("issued_to_name")
            if recipient_id is None and not recipient_name:
                raise ValueError("ISSUE and ISSUE_RETURN require recipient_id or recipient_name")
        for line in lines:
            if line.qty <= 0:
                raise ValueError(f"{operation_type} operations require positive qty values")
        return lines

    @model_validator(mode="after")
    def validate_client_request_id_for_temporary_items(self) -> "OperationCreate":
        has_temporary_items = any(line.temporary_item is not None for line in self.lines)
        if has_temporary_items and not self.client_request_id:
            raise ValueError("client_request_id is required when temporary_item lines are used")
        return self

    @field_validator("recipient_name_snapshot")
    @classmethod
    def validate_recipient_name_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("recipient_name_snapshot must not be blank")
        return value.strip()


class OperationUpdate(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)
    effective_at: datetime | None = None
    source_site_id: int | None = None
    destination_site_id: int | None = Field(default=None, validation_alias=AliasChoices("destination_site_id", "target_site_id"))
    issued_to_user_id: UUID | None = None
    issued_to_name: str | None = Field(default=None, max_length=255)
    recipient_id: int | None = None
    recipient_name_snapshot: str | None = Field(
        default=None,
        validation_alias=AliasChoices("recipient_name_snapshot", "recipient_name", "issued_to_name"),
        max_length=255,
    )
    lines: list[OperationLineCreate] | None = None


class OperationEffectiveAtUpdate(BaseModel):
    effective_at: datetime


class OperationSubmit(BaseModel):
    submit: bool = True


class OperationCancel(BaseModel):
    cancel: bool = True
    reason: str | None = Field(default=None, max_length=500)


class OperationLineResponse(ORMBaseModel):
    id: int
    line_number: int
    item_id: int
    temporary_item_id: int | None = None
    temporary_item_status: str | None = None
    resolved_item_id: int | None = None
    qty: int = Field(validation_alias=AliasChoices("qty", "quantity"))
    accepted_qty: Decimal = Decimal("0")
    lost_qty: Decimal = Decimal("0")
    batch: str | None = None
    comment: str | None = Field(default=None, validation_alias=AliasChoices("comment", "notes"))

    @property
    def quantity(self) -> int:
        return self.qty

    @property
    def notes(self) -> str | None:
        return self.comment

    @property
    def pending_qty(self) -> Decimal:
        return Decimal(self.qty) - Decimal(self.accepted_qty) - Decimal(self.lost_qty)


class OperationResponse(ORMBaseModel):
    id: UUID = Field(validation_alias=AliasChoices("id", "operation_uuid"))
    site_id: int
    operation_type: OperationType = Field(validation_alias=AliasChoices("operation_type", "type"))
    status: OperationStatus
    effective_at: datetime | None = None
    source_site_id: int | None = None
    destination_site_id: int | None = Field(default=None, validation_alias=AliasChoices("destination_site_id", "target_site_id"))
    issued_to_user_id: UUID | None = None
    issued_to_name: str | None = None
    recipient_id: int | None = None
    recipient_name_snapshot: str | None = None
    acceptance_required: bool = False
    acceptance_state: AcceptanceState = "not_required"
    acceptance_resolved_at: datetime | None = None
    acceptance_resolved_by_user_id: UUID | None = None
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
    effective_after: datetime | None = None
    effective_before: datetime | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    updated_after: datetime | None = None
    updated_before: datetime | None = None
    search: str | None = None

    model_config = ConfigDict(extra="forbid")

    @property
    def type(self) -> OperationType | None:
        return self.operation_type
