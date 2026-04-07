from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ORMBaseModel


class ItemMovementFilter(BaseModel):
    site_id: int | None = None
    item_id: int | None = None
    category_id: int | None = None
    search: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class ItemMovementRow(ORMBaseModel):
    site_id: int
    site_name: str
    item_id: int
    item_name: str
    sku: str | None = None
    unit_id: int
    unit_symbol: str
    category_id: int
    category_name: str
    incoming_qty: Decimal
    outgoing_qty: Decimal
    net_qty: Decimal
    last_operation_at: datetime | None = None


class ItemMovementReportResponse(ORMBaseModel):
    items: list[ItemMovementRow]
    total_count: int
    page: int
    page_size: int
    date_from: datetime | None = None
    date_to: datetime | None = None


class StockSummaryFilter(BaseModel):
    site_id: int | None = None
    category_id: int | None = None
    search: str | None = None
    only_positive: bool = Field(default=False, description="Show only positive balances")

    model_config = ConfigDict(extra="forbid")


class StockSummaryRow(ORMBaseModel):
    site_id: int
    site_name: str
    items_count: int
    positive_items_count: int
    total_quantity: Decimal
    last_balance_at: datetime | None = None


class StockSummaryReportResponse(ORMBaseModel):
    items: list[StockSummaryRow]
    total_count: int
    page: int
    page_size: int
