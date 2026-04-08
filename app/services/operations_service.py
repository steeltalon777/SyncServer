from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status

from app.schemas.operation import OperationCreate, OperationType, OperationUpdate
from app.services.uow import UnitOfWork

logger = logging.getLogger(__name__)

SUPPORTED_OPERATION_TYPES: set[OperationType] = {
    "RECEIVE",
    "EXPENSE",
    "WRITE_OFF",
    "MOVE",
    "ADJUSTMENT",
    "ISSUE",
    "ISSUE_RETURN",
}
DECREMENT_OPERATION_TYPES: set[OperationType] = {"EXPENSE", "WRITE_OFF"}
ISSUE_STUB_OPERATION_TYPES: set[OperationType] = {"ISSUE", "ISSUE_RETURN"}


class OperationsService:
    """Operation domain service with strict server-side validation."""

    @staticmethod
    async def _ensure_sufficient_balance(
        uow: UnitOfWork,
        *,
        site_id: int,
        item_id: int,
        required_qty: Decimal,
        error_message: str,
    ) -> None:
        balance = await uow.balances.get_for_update(site_id=site_id, item_id=item_id)
        current_qty = balance.qty if balance is not None else Decimal("0")
        if current_qty < required_qty:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_message)

    @staticmethod
    async def _validate_operation_type(operation_type: OperationType) -> None:
        if operation_type not in SUPPORTED_OPERATION_TYPES:
            supported = ", ".join(sorted(SUPPORTED_OPERATION_TYPES))
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unsupported operation_type '{operation_type}', supported: {supported}",
            )

    @staticmethod
    async def _apply_balance_delta(
        uow: UnitOfWork,
        *,
        site_id: int,
        item_id: int,
        quantity_delta: Decimal,
        error_context: str,
    ) -> None:
        if quantity_delta < 0:
            await OperationsService._ensure_sufficient_balance(
                uow,
                site_id=site_id,
                item_id=item_id,
                required_qty=abs(quantity_delta),
                error_message=(
                    f"insufficient stock for {error_context}: "
                    f"item={item_id}, site={site_id}, required={abs(quantity_delta)}"
                ),
            )
        await uow.balances.update_balance_quantity(
            site_id=site_id,
            item_id=item_id,
            quantity_delta=quantity_delta,
        )

    @staticmethod
    async def _validate_operation_sites(uow: UnitOfWork, operation_data: OperationCreate) -> None:
        site = await uow.sites.get_by_id(operation_data.site_id)
        if not site:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="site not found")

        if operation_data.operation_type == "MOVE":
            if operation_data.source_site_id is None or operation_data.destination_site_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="MOVE operation requires source_site_id and destination_site_id",
                )
            if operation_data.source_site_id == operation_data.destination_site_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="MOVE source and destination must be different",
                )

            source = await uow.sites.get_by_id(operation_data.source_site_id)
            if not source:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source site not found")
            destination = await uow.sites.get_by_id(operation_data.destination_site_id)
            if not destination:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="destination site not found")

    @staticmethod
    def _validate_line_quantities(
        operation_type: OperationType,
        lines,
    ) -> None:
        if operation_type == "ADJUSTMENT":
            return
        for line in lines:
            if line.qty <= 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"{operation_type} operations require positive qty values",
                )

    @staticmethod
    async def create_operation(
        uow: UnitOfWork,
        operation_data: OperationCreate,
        user_id: UUID,
    ) -> dict[str, object]:
        await OperationsService._validate_operation_type(operation_data.operation_type)
        await OperationsService._validate_operation_sites(uow, operation_data)
        OperationsService._validate_line_quantities(operation_data.operation_type, operation_data.lines)

        for line in operation_data.lines:
            item = await uow.catalog.get_item_by_id(line.item_id)
            if not item:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"item with id {line.item_id} not found",
                )

        operation = await uow.operations.create_operation(
            site_id=operation_data.site_id,
            operation_type=operation_data.operation_type,
            effective_at=operation_data.effective_at or datetime.now(UTC),
            source_site_id=operation_data.source_site_id,
            destination_site_id=operation_data.destination_site_id,
            issued_to_user_id=operation_data.issued_to_user_id,
            issued_to_name=operation_data.issued_to_name,
            created_by_user_id=user_id,
            notes=operation_data.notes,
        )

        for line_data in operation_data.lines:
            await uow.operations.create_operation_line(
                operation_id=operation.id,
                line_number=line_data.line_number,
                item_id=line_data.item_id,
                qty=line_data.qty,
                batch=line_data.batch,
                comment=line_data.comment,
            )

        created_operation = await uow.operations.get_operation_by_id(operation.id)
        return {"operation": created_operation}

    @staticmethod
    async def update_operation_effective_at(
        uow: UnitOfWork,
        operation_id: UUID,
        *,
        effective_at: datetime,
    ):
        operation = await uow.operations.get_operation_by_id(operation_id)
        if not operation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="operation not found")
        if operation.status == "cancelled":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cannot change effective_at for cancelled operation",
            )

        updated = await uow.operations.update_operation(
            operation_id=operation_id,
            effective_at=effective_at,
            fields_set={"effective_at"},
        )
        return await uow.operations.get_operation_by_id(updated.id)

    @staticmethod
    async def update_operation(
        uow: UnitOfWork,
        operation_id: UUID,
        update_data: OperationUpdate,
    ):
        operation = await uow.operations.get_operation_by_id(operation_id)
        if not operation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="operation not found")
        if operation.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"cannot update operation with status {operation.status}",
            )

        source_site_id = operation.source_site_id
        destination_site_id = operation.destination_site_id
        if "source_site_id" in update_data.model_fields_set:
            source_site_id = update_data.source_site_id
        if "destination_site_id" in update_data.model_fields_set:
            destination_site_id = update_data.destination_site_id

        if operation.operation_type == "MOVE":
            if source_site_id is None or destination_site_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="MOVE operation requires source_site_id and destination_site_id",
                )
            if source_site_id == destination_site_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="MOVE source and destination must be different",
                )
        if update_data.lines is not None:
            OperationsService._validate_line_quantities(operation.operation_type, update_data.lines)

        updated = await uow.operations.update_operation(
            operation_id=operation_id,
            notes=update_data.notes,
            effective_at=update_data.effective_at,
            source_site_id=source_site_id,
            destination_site_id=destination_site_id,
            issued_to_user_id=update_data.issued_to_user_id,
            issued_to_name=update_data.issued_to_name,
            fields_set=update_data.model_fields_set,
        )

        if update_data.lines is not None:
            await uow.operations.delete_operation_lines(operation_id)
            for line in update_data.lines:
                item = await uow.catalog.get_item_by_id(line.item_id)
                if not item:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"item with id {line.item_id} not found",
                    )
                await uow.operations.create_operation_line(
                    operation_id=operation_id,
                    line_number=line.line_number,
                    item_id=line.item_id,
                    qty=line.qty,
                    batch=line.batch,
                    comment=line.comment,
                )

        return await uow.operations.get_operation_by_id(updated.id)

    @staticmethod
    async def submit_operation(
        uow: UnitOfWork,
        operation_id: UUID,
        user_id: UUID,
    ) -> dict[str, object]:
        operation = await uow.operations.get_operation_by_id(operation_id)
        if not operation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="operation not found")
        if operation.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"operation is already {operation.status}",
            )
        if operation.operation_type in ISSUE_STUB_OPERATION_TYPES:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"{operation.operation_type} submit is not implemented yet",
            )

        for line in operation.lines:
            quantity = Decimal(line.qty)
            if operation.operation_type == "RECEIVE":
                await uow.balances.update_balance_quantity(
                    site_id=operation.site_id,
                    item_id=line.item_id,
                    quantity_delta=quantity,
                )
            elif operation.operation_type in DECREMENT_OPERATION_TYPES:
                await OperationsService._ensure_sufficient_balance(
                    uow,
                    site_id=operation.site_id,
                    item_id=line.item_id,
                    required_qty=quantity,
                    error_message=(
                        f"insufficient stock for {operation.operation_type}: item={line.item_id}, "
                        f"site={operation.site_id}, required={line.qty}"
                    ),
                )
                await uow.balances.update_balance_quantity(
                    site_id=operation.site_id,
                    item_id=line.item_id,
                    quantity_delta=-quantity,
                )
            elif operation.operation_type == "ADJUSTMENT":
                if quantity < 0:
                    await OperationsService._ensure_sufficient_balance(
                        uow,
                        site_id=operation.site_id,
                        item_id=line.item_id,
                        required_qty=abs(quantity),
                        error_message=(
                            f"insufficient stock for ADJUSTMENT: item={line.item_id}, "
                            f"site={operation.site_id}, delta={line.qty}"
                        ),
                    )
                await uow.balances.update_balance_quantity(
                    site_id=operation.site_id,
                    item_id=line.item_id,
                    quantity_delta=quantity,
                )
            elif operation.operation_type == "MOVE":
                if operation.source_site_id is None or operation.destination_site_id is None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="MOVE operation requires source_site_id and destination_site_id",
                    )

                await OperationsService._ensure_sufficient_balance(
                    uow,
                    site_id=operation.source_site_id,
                    item_id=line.item_id,
                    required_qty=quantity,
                    error_message=(
                        f"insufficient stock for MOVE: item={line.item_id}, "
                        f"source_site={operation.source_site_id}, required={line.qty}"
                    ),
                )
                await uow.balances.update_balance_quantity(
                    site_id=operation.source_site_id,
                    item_id=line.item_id,
                    quantity_delta=-quantity,
                )
                await uow.balances.update_balance_quantity(
                    site_id=operation.destination_site_id,
                    item_id=line.item_id,
                    quantity_delta=quantity,
                )

        submitted_operation = await uow.operations.submit_operation(
            operation_id=operation_id,
            submitted_by_user_id=user_id,
        )
        return {"operation": submitted_operation}

    @staticmethod
    async def cancel_operation(
        uow: UnitOfWork,
        operation_id: UUID,
        user_id: UUID,
        reason: str | None = None,
    ) -> dict[str, object]:
        operation = await uow.operations.get_operation_by_id(operation_id)
        if not operation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="operation not found")
        if operation.status == "cancelled":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="operation is already cancelled")

        if operation.status == "submitted":
            if operation.operation_type in ISSUE_STUB_OPERATION_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_501_NOT_IMPLEMENTED,
                    detail=f"{operation.operation_type} cancel rollback is not implemented yet",
                )
            for line in operation.lines:
                quantity = Decimal(line.qty)
                if operation.operation_type == "RECEIVE":
                    await OperationsService._apply_balance_delta(
                        uow,
                        site_id=operation.site_id,
                        item_id=line.item_id,
                        quantity_delta=-quantity,
                        error_context="RECEIVE rollback",
                    )
                elif operation.operation_type in DECREMENT_OPERATION_TYPES:
                    await OperationsService._apply_balance_delta(
                        uow,
                        site_id=operation.site_id,
                        item_id=line.item_id,
                        quantity_delta=quantity,
                        error_context=f"{operation.operation_type} rollback",
                    )
                elif operation.operation_type == "ADJUSTMENT":
                    await OperationsService._apply_balance_delta(
                        uow,
                        site_id=operation.site_id,
                        item_id=line.item_id,
                        quantity_delta=-quantity,
                        error_context="ADJUSTMENT rollback",
                    )
                elif operation.operation_type == "MOVE":
                    if operation.source_site_id and operation.destination_site_id:
                        await OperationsService._ensure_sufficient_balance(
                            uow,
                            site_id=operation.destination_site_id,
                            item_id=line.item_id,
                            required_qty=quantity,
                            error_message=(
                                f"insufficient stock for MOVE rollback from destination: "
                                f"item={line.item_id}, site={operation.destination_site_id}, required={line.qty}"
                            ),
                        )
                        await OperationsService._apply_balance_delta(
                            uow,
                            site_id=operation.source_site_id,
                            item_id=line.item_id,
                            quantity_delta=quantity,
                            error_context="MOVE rollback to source",
                        )
                        await OperationsService._apply_balance_delta(
                            uow,
                            site_id=operation.destination_site_id,
                            item_id=line.item_id,
                            quantity_delta=-quantity,
                            error_context="MOVE rollback from destination",
                        )

        cancelled_operation = await uow.operations.cancel_operation(
            operation_id=operation_id,
            cancelled_by_user_id=user_id,
        )

        logger.info("cancelled operation=%s by user=%s reason=%s", operation_id, user_id, reason)
        return {"operation": cancelled_operation}
