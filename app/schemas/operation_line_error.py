from __future__ import annotations

from pydantic import BaseModel, Field


class OperationLineError(BaseModel):
    """Structured error for a single operation line in create/update."""

    line_number: int
    item_id: int | None = None
    reason: str  # item_not_found, deleted, inactive, duplicate_item, unit_unusable, category_unusable
    first_line_number: int | None = None  # for duplicate_item: the first line with the same canonical item


class OperationLinesInvalidResponse(BaseModel):
    """Response body when create/update rejects all lines due to validation errors."""

    code: str = "operation_lines_invalid"
    message: str = "One or more operation lines are invalid"
    operation_id: str | None = None
    lines: list[OperationLineError] = Field(default_factory=list)
