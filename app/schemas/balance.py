from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.schemas.common import ORMBaseModel


class BalanceResponse(ORMBaseModel):
    """UI-ready balance row."""

    site_id: int
    site_name: str
    item_id: int
    item_name: str
    sku: str | None = None
    unit_id: int
    unit_symbol: str
    category_id: int
    category_name: str
    qty: Decimal = Field(validation_alias=AliasChoices("qty", "quantity"))
    updated_at: datetime


class BalanceListResponse(ORMBaseModel):
    items: list[BalanceResponse]
    total_count: int
    page: int
    page_size: int


class BalanceSummaryData(ORMBaseModel):
    rows_count: int
    sites_count: int
    total_quantity: float


class BalanceSummaryResponse(ORMBaseModel):
    accessible_sites_count: int
    summary: BalanceSummaryData


class BalanceFilter(BaseModel):
    site_id: int | None = None
    item_id: int | None = None
    category_id: int | None = None
    search: str | None = None
    only_positive: bool = Field(default=False, description="Show only positive balances")

    model_config = ConfigDict(extra="forbid")
