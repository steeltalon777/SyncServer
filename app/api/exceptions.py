from __future__ import annotations

from fastapi import HTTPException, status


class SyncServerException(HTTPException):
    """Base exception for SyncServer API."""
    
    def __init__(
        self,
        status_code: int,
        detail: str,
        error_code: str | None = None,
        details: dict | None = None,
    ):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code or f"HTTP_{status_code}"
        self.details = details


class ValidationError(SyncServerException):
    """Validation error (400)."""
    
    def __init__(self, detail: str, details: dict | None = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            error_code="VALIDATION_ERROR",
            details=details,
        )


class UnauthorizedError(SyncServerException):
    """Unauthorized error (401)."""
    
    def __init__(self, detail: str = "Unauthorized"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code="UNAUTHORIZED",
        )


class ForbiddenError(SyncServerException):
    """Forbidden error (403)."""
    
    def __init__(self, detail: str = "Forbidden"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            error_code="FORBIDDEN",
        )


class NotFoundError(SyncServerException):
    """Not found error (404)."""
    
    def __init__(self, resource: str, resource_id: str | int):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} not found: {resource_id}",
            error_code="NOT_FOUND",
        )


class ConflictError(SyncServerException):
    """Conflict error (409)."""
    
    def __init__(self, detail: str, details: dict | None = None):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            error_code="CONFLICT",
            details=details,
        )


class RateLimitError(SyncServerException):
    """Rate limit error (429)."""
    
    def __init__(self, detail: str = "Rate limit exceeded"):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            error_code="RATE_LIMIT_EXCEEDED",
        )


class InternalServerError(SyncServerException):
    """Internal server error (500)."""
    
    def __init__(self, detail: str = "Internal server error"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            error_code="INTERNAL_SERVER_ERROR",
        )


# Permission-related errors
class PermissionDeniedError(ForbiddenError):
    """Permission denied error."""
    
    def __init__(self, action: str, resource: str):
        super().__init__(detail=f"Permission denied: cannot {action} {resource}")


class RolePermissionError(ForbiddenError):
    """Role permission error."""
    
    def __init__(self, required_role: str, user_role: str):
        super().__init__(
            detail=f"Required role: {required_role}, user role: {user_role}",
        )


# Business logic errors
class OperationStateError(ConflictError):
    """Operation state error."""
    
    def __init__(self, operation_id: int, current_status: str, required_status: str):
        super().__init__(
            detail=f"Operation {operation_id} is {current_status}, must be {required_status}",
        )


class BalanceInsufficientError(ConflictError):
    """Insufficient balance error."""
    
    def __init__(self, site_id: str, item_id: int, available: int, requested: int):
        super().__init__(
            detail=f"Insufficient balance for item {item_id} at site {site_id}: "
                   f"available {available}, requested {requested}",
        )


# Catalog errors
class CategoryCycleError(ConflictError):
    """Category hierarchy cycle error."""
    
    def __init__(self, category_id: int, parent_id: int):
        super().__init__(
            detail=f"Creating category {category_id} under parent {parent_id} would create a cycle",
        )


class UniqueConstraintError(ConflictError):
    """Unique constraint violation error."""
    
    def __init__(self, field: str, value: str):
        super().__init__(
            detail=f"{field} '{value}' already exists",
        )