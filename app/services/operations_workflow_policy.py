from __future__ import annotations

from fastapi import HTTPException, status


class OperationsWorkflowPolicy:
    """Status and acceptance-state guards for operation workflow transitions."""

    @staticmethod
    def require_exists(operation) -> None:
        if not operation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="operation not found")

    @staticmethod
    def require_not_cancelled_for_effective_at_change(operation) -> None:
        if operation.status == "cancelled":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cannot change effective_at for cancelled operation",
            )

    @staticmethod
    def require_draft_for_update(operation) -> None:
        if operation.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"cannot update operation with status {operation.status}",
            )

    @staticmethod
    def require_draft_for_submit(operation) -> None:
        if operation.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"operation is already {operation.status}",
            )

    @staticmethod
    def require_submitted_for_acceptance(operation) -> None:
        if operation.status != "submitted":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="only submitted operations can be accepted")

    @staticmethod
    def require_acceptance_required(operation) -> None:
        if not operation.acceptance_required:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="operation does not require acceptance",
            )

    @staticmethod
    def require_acceptance_not_resolved(operation) -> None:
        if operation.acceptance_state == "resolved":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="operation is already fully accepted")

    @staticmethod
    def require_not_cancelled_for_cancel(operation) -> None:
        if operation.status == "cancelled":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="operation is already cancelled")
