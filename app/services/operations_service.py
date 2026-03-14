from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from app.schemas.operation import OperationCreate
from app.services.uow import UnitOfWork

logger = logging.getLogger(__name__)


class OperationsService:
    """Service for operation business logic.

    Permission checks must be handled in API layer via AccessGuard / AccessService.
    This service is responsible only for business validation and execution.
    """

    @staticmethod
    async def _ensure_sufficient_balance(
        uow: UnitOfWork,
        *,
        site_id: UUID,
        item_id: UUID,
        required_qty: Decimal,
        error_message: str,
    ) -> None:
        balance = await uow.balances.get_for_update(site_id=site_id, item_id=item_id)
        current_qty = balance.qty if balance is not None else Decimal("0")
        if current_qty < required_qty:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_message,
            )

    @staticmethod
    async def create_operation(
        uow: UnitOfWork,
        operation_data: OperationCreate,
        user_id: int,
    ) -> dict:
        """Create a new operation with business validation."""
        site = await uow.sites.get_by_id(operation_data.site_id)
        if not site:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Site not found",
            )

        for line in operation_data.lines:
            item = await uow.catalog.get_item_by_id(line.item_id)
            if not item:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Item with ID {line.item_id} not found",
                )

            if operation_data.type == "MOVE":
                if not line.source_site_id or not line.target_site_id:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="MOVE operations require source_site_id and target_site_id",
                    )

                source_site = await uow.sites.get_by_id(line.source_site_id)
                if not source_site:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Source site {line.source_site_id} not found",
                    )

                target_site = await uow.sites.get_by_id(line.target_site_id)
                if not target_site:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Target site {line.target_site_id} not found",
                    )

        operation_uuid = uuid4()
        operation = await uow.operations.create_operation(
            operation_uuid=operation_uuid,
            site_id=operation_data.site_id,
            type=operation_data.type,
            created_by_user_id=user_id,
            notes=operation_data.notes,
        )

        for line_data in operation_data.lines:
            await uow.operations.create_operation_line(
                operation_id=operation.id,
                line_number=line_data.line_number,
                item_id=line_data.item_id,
                quantity=line_data.quantity,
                source_site_id=line_data.source_site_id,
                target_site_id=line_data.target_site_id,
                notes=line_data.notes,
            )

        created_operation = await uow.operations.get_operation_by_id(operation.id)

        logger.info(
            "Created operation %s of type %s by user %s for site %s with %s lines",
            operation_uuid,
            operation_data.type,
            user_id,
            operation_data.site_id,
            len(operation_data.lines),
        )

        return {
            "operation": created_operation,
            "operation_uuid": operation_uuid,
        }

    @staticmethod
    async def submit_operation(
        uow: UnitOfWork,
        operation_id: int,
        user_id: int,
    ) -> dict:
        """Submit an operation and update balances atomically inside the current UoW transaction."""
        operation = await uow.operations.get_operation_by_id(operation_id)
        if not operation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Operation not found",
            )

        if operation.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Operation is already {operation.status}",
            )

        for line in operation.lines:
            quantity = Decimal(line.quantity)

            if operation.type == "RECEIVE":
                await uow.balances.update_balance_quantity(
                    site_id=operation.site_id,
                    item_id=line.item_id,
                    quantity_delta=quantity,
                )
            elif operation.type == "WRITE_OFF":
                await OperationsService._ensure_sufficient_balance(
                    uow,
                    site_id=operation.site_id,
                    item_id=line.item_id,
                    required_qty=quantity,
                    error_message=(
                        f"Insufficient stock for WRITE_OFF: item={line.item_id}, "
                        f"site={operation.site_id}, required={line.quantity}"
                    ),
                )
                await uow.balances.update_balance_quantity(
                    site_id=operation.site_id,
                    item_id=line.item_id,
                    quantity_delta=-quantity,
                )
            elif operation.type == "MOVE":
                if not line.source_site_id or not line.target_site_id:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="MOVE operation line must have source_site_id and target_site_id",
                    )

                target_site = await uow.sites.get_by_id(line.target_site_id)
                if not target_site:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Target site {line.target_site_id} not found",
                    )

                await OperationsService._ensure_sufficient_balance(
                    uow,
                    site_id=line.source_site_id,
                    item_id=line.item_id,
                    required_qty=quantity,
                    error_message=(
                        f"Insufficient stock for MOVE: item={line.item_id}, "
                        f"source_site={line.source_site_id}, required={line.quantity}"
                    ),
                )
                await uow.balances.update_balance_quantity(
                    site_id=line.source_site_id,
                    item_id=line.item_id,
                    quantity_delta=-quantity,
                )
                await uow.balances.update_balance_quantity(
                    site_id=line.target_site_id,
                    item_id=line.item_id,
                    quantity_delta=quantity,
                )

        submitted_operation = await uow.operations.submit_operation(
            operation_id=operation_id,
            submitted_by_user_id=user_id,
        )

        logger.info(
            "Submitted operation %s by user %s",
            operation.operation_uuid,
            user_id,
        )

        return {"operation": submitted_operation}

    @staticmethod
    async def cancel_operation(
        uow: UnitOfWork,
        operation_id: int,
        user_id: int,
        reason: str | None = None,
    ) -> dict:
        """Cancel an operation and reverse balance changes if submitted."""
        operation = await uow.operations.get_operation_by_id(operation_id)
        if not operation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Operation not found",
            )

        if operation.status == "cancelled":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Operation is already cancelled",
            )

        if operation.status == "submitted":
            for line in operation.lines:
                quantity = Decimal(line.quantity)
                if operation.type == "RECEIVE":
                    await uow.balances.update_balance_quantity(
                        site_id=operation.site_id,
                        item_id=line.item_id,
                        quantity_delta=-quantity,
                    )
                elif operation.type == "WRITE_OFF":
                    await uow.balances.update_balance_quantity(
                        site_id=operation.site_id,
                        item_id=line.item_id,
                        quantity_delta=quantity,
                    )
                elif operation.type == "MOVE":
                    if line.source_site_id and line.target_site_id:
                        await uow.balances.update_balance_quantity(
                            site_id=line.source_site_id,
                            item_id=line.item_id,
                            quantity_delta=quantity,
                        )
                        await uow.balances.update_balance_quantity(
                            site_id=line.target_site_id,
                            item_id=line.item_id,
                            quantity_delta=-quantity,
                        )

        cancelled_operation = await uow.operations.cancel_operation(
            operation_id=operation_id,
            cancelled_by_user_id=user_id,
        )

        logger.info(
            "Cancelled operation %s by user %s, reason: %s",
            operation.operation_uuid,
            user_id,
            reason,
        )

        return {"operation": cancelled_operation}
