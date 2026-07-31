from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ItemRef(BaseModel):
    id: int
    name: str


class SiteRef(BaseModel):
    id: int
    name: str


class IssueObjectRef(BaseModel):
    id: int
    name: str


class UnitRef(BaseModel):
    id: int
    name: str
    symbol: str


class ProblemErrorScope(BaseModel):
    scope: Literal["operation", "line_group"]


# --- line_group codes (обязательные поля) ---


class InsufficientStockError(ProblemErrorScope):
    code: Literal["insufficient_stock"]
    scope: Literal["line_group"]
    operation_line_ids: list[int]
    item: ItemRef
    stock_site: SiteRef
    required_qty: str  # Decimal as string
    available_qty: str
    unit: UnitRef | None = None  # display-only


class InsufficientIssuedBalanceError(ProblemErrorScope):
    code: Literal["insufficient_issued_balance"]
    scope: Literal["line_group"]
    operation_line_ids: list[int]
    item: ItemRef
    issue_object: IssueObjectRef
    required_qty: str
    available_qty: str
    unit: UnitRef | None = None


# --- operation codes (обязательные поля) ---


class StaleVersionError(ProblemErrorScope):
    code: Literal["stale_version"]
    scope: Literal["operation"]
    expected_version: int
    actual_version: int


class OperationInWrongStateError(ProblemErrorScope):
    code: Literal["operation_in_wrong_state"]
    scope: Literal["operation"]
    current_state: str
    allowed_states: list[str]


class RoleNotPermittedError(ProblemErrorScope):
    code: Literal["role_not_permitted"]
    scope: Literal["operation"]


class OperationNotFoundError(ProblemErrorScope):
    code: Literal["operation_not_found"]
    scope: Literal["operation"]


# --- envelope ---

ProblemError = Annotated[
    InsufficientStockError
    | InsufficientIssuedBalanceError
    | StaleVersionError
    | OperationInWrongStateError
    | RoleNotPermittedError
    | OperationNotFoundError,
    Field(discriminator="code"),
]


class ProblemEnvelope(BaseModel):
    type: str  # "urn:warehouse:problem:<class>"
    title: str
    status: int
    code: str  # верхнеуровневый
    detail: str  # строка для legacy
    instance: str | None = None
    trace_id: str | None = None
    errors: list[ProblemError] = Field(default_factory=list)
