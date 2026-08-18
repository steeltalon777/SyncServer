from __future__ import annotations

from uuid import UUID

from app.schemas.operation_line_error import OperationLineError, OperationLinesInvalidResponse


class OperationLinesInvalidError(Exception):
    """Raised when create/update rejects all lines due to validation errors."""

    def __init__(
        self,
        errors: list[OperationLineError],
        operation_id: UUID | None = None,
        message: str = "One or more operation lines are invalid",
    ):
        self.errors = errors
        self.operation_id = operation_id
        self.message = message
        super().__init__(message)

    def to_response(self) -> OperationLinesInvalidResponse:
        return OperationLinesInvalidResponse(
            message=self.message,
            operation_id=str(self.operation_id) if self.operation_id else None,
            lines=self.errors,
        )
