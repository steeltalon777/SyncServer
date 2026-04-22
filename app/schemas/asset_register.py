from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ORMBaseModel


class OperationAcceptLinePayload(BaseModel):
    line_id: int
    accepted_qty: Decimal = Field(default=Decimal("0"), ge=0)
    lost_qty: Decimal = Field(default=Decimal("0"), ge=0)
    note: str | None = Field(default=None, max_length=500)


class OperationAcceptLinesRequest(BaseModel):
    lines: list[OperationAcceptLinePayload] = Field(min_length=1)


class PendingAcceptanceFilter(BaseModel):
    site_id: int | None = None
    operation_id: UUID | None = None
    item_id: int | None = None
    search: str | None = None

    model_config = ConfigDict(extra="forbid")


class PendingAcceptanceRow(ORMBaseModel):
    operation_id: UUID
    operation_line_id: int
    destination_site_id: int
    destination_site_name: str
    source_site_id: int | None = None
    item_id: int
    item_name: str
    sku: str | None = None
    qty: Decimal
    updated_at: datetime


class PendingAcceptanceListResponse(ORMBaseModel):
    items: list[PendingAcceptanceRow]
    total_count: int
    page: int
    page_size: int


class LostAssetFilter(BaseModel):
    site_id: int | None = None
    source_site_id: int | None = None
    operation_id: UUID | None = None
    item_id: int | None = None
    search: str | None = None
    updated_after: datetime | None = None
    updated_before: datetime | None = None
    qty_from: Decimal | None = Field(None, ge=0)
    qty_to: Decimal | None = Field(None, ge=0)

    model_config = ConfigDict(extra="forbid")


class LostAssetRow(ORMBaseModel):
    operation_id: UUID
    operation_line_id: int
    site_id: int
    site_name: str
    source_site_id: int | None = None
    source_site_name: str | None = None
    item_id: int
    item_name: str
    sku: str | None = None
    qty: Decimal
    updated_at: datetime


class LostAssetListResponse(ORMBaseModel):
    items: list[LostAssetRow]
    total_count: int
    page: int
    page_size: int


class LostAssetResolveRequest(BaseModel):
    action: Literal["found_to_destination", "return_to_source", "write_off"]
    qty: Decimal = Field(gt=0)
    note: str | None = Field(default=None, max_length=500)
    responsible_recipient_id: int | None = None


class IssuedAssetFilter(BaseModel):
    recipient_id: int | None = None
    item_id: int | None = None
    search: str | None = None

    model_config = ConfigDict(extra="forbid")


class IssuedAssetRow(ORMBaseModel):
    recipient_id: int
    recipient_name: str
    recipient_type: str
    item_id: int
    item_name: str
    sku: str | None = None
    qty: Decimal
    updated_at: datetime


class IssuedAssetListResponse(ORMBaseModel):
    items: list[IssuedAssetRow]
    total_count: int
    page: int
    page_size: int
