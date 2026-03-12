from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from app.schemas.operation import OperationCreate, OperationUpdate
from app.services.uow import UnitOfWork

logger = logging.getLogger(__name__)


class OperationsService:
    """Service for operation business logic."""

    @staticmethod
    async def validate_operation_permissions(
        uow: UnitOfWork,
        user_id: int,
        site_id: UUID,
        required_role: str | None = None,
    ) -> bool:
        """Validate user permissions for operation on a site."""
        # Get user's roles for the site
        user_site_role = await uow.user_site_roles.get_by_user_and_site(user_id, site_id)
        
        if not user_site_role:
            return False
        
        # Check if user has required role
        if required_role:
            role_hierarchy = {"storekeeper": 1, "chief_storekeeper": 2, "root": 3}
            user_role_level = role_hierarchy.get(user_site_role.role, 0)
            required_role_level = role_hierarchy.get(required_role, 0)
            
            if user_role_level < required_role_level:
                return False
        
        return True

    @staticmethod
    async def create_operation(
        uow: UnitOfWork,
        operation_data: OperationCreate,
        user_id: int,
    ) -> dict:
        """Create a new operation with validation."""
        # Validate user permissions for the site
        if not await OperationsService.validate_operation_permissions(
            uow, user_id, operation_data.site_id, "storekeeper"
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have permission to create operations for this site",
            )
        
        # Validate site exists
        site = await uow.sites.get_by_id(operation_data.site_id)
        if not site:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Site not found",
            )
        
        # Validate items exist
        for line in operation_data.lines:
            item = await uow.catalog.get_item_by_id(line.item_id)
            if not item:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Item with ID {line.item_id} not found",
                )
            
            # For MOVE operations, validate source and target sites
            if operation_data.type == "MOVE":
                if not line.source_site_id or not line.target_site_id:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="MOVE operations require source_site_id and target_site_id",
                    )
                
                # Validate source site exists
                source_site = await uow.sites.get_by_id(line.source_site_id)
                if not source_site:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Source site {line.source_site_id} not found",
                    )
                
                # Validate target site exists
                target_site = await uow.sites.get_by_id(line.target_site_id)
                if not target_site:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Target site {line.target_site_id} not found",
                    )
                
                # Check if user has access to source site
                if not await OperationsService.validate_operation_permissions(
                    uow, user_id, line.source_site_id, "storekeeper"
                ):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"User does not have permission to move from site {line.source_site_id}",
                    )
        
        # Create operation
        operation_uuid = uuid4()
        operation = await uow.operations.create_operation(
            operation_uuid=operation_uuid,
            site_id=operation_data.site_id,
            type=operation_data.type,
            created_by_user_id=user_id,
            notes=operation_data.notes,
        )
        
        # Create operation lines
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
        
        # Get the complete operation with lines
        created_operation = await uow.operations.get_operation_by_id(operation.id)
        
        logger.info(
            f"Created operation {operation_uuid} of type {operation_data.type} "
            f"by user {user_id} for site {operation_data.site_id} with {len(operation_data.lines)} lines"
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
        """Submit an operation and update balances."""
        operation = await uow.operations.get_operation_by_id(operation_id)
        if not operation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Operation not found",
            )
        
        # Check if user can submit this operation
        if not await OperationsService.validate_operation_permissions(
            uow, user_id, operation.site_id, "storekeeper"
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have permission to submit this operation",
            )
        
        # Check operation status
        if operation.status != "draft":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Operation is already {operation.status}",
            )
        
        # Update balances based on operation type
        for line in operation.lines:
            if operation.type == "RECEIVE":
                # Increase balance at operation site
                await uow.balances.update_balance_quantity(
                    site_id=operation.site_id,
                    item_id=line.item_id,
                    quantity_delta=Decimal(line.quantity),
                )
            elif operation.type == "WRITE_OFF":
                # Decrease balance at operation site
                await uow.balances.update_balance_quantity(
                    site_id=operation.site_id,
                    item_id=line.item_id,
                    quantity_delta=Decimal(-line.quantity),
                )
            elif operation.type == "MOVE":
                if line.source_site_id and line.target_site_id:
                    # Decrease from source, increase at target
                    await uow.balances.update_balance_quantity(
                        site_id=line.source_site_id,
                        item_id=line.item_id,
                        quantity_delta=Decimal(-line.quantity),
                    )
                    await uow.balances.update_balance_quantity(
                        site_id=line.target_site_id,
                        item_id=line.item_id,
                        quantity_delta=Decimal(line.quantity),
                    )
            elif operation.type == "ISSUE":
                # Decrease balance at operation site
                await uow.balances.update_balance_quantity(
                    site_id=operation.site_id,
                    item_id=line.item_id,
                    quantity_delta=Decimal(-line.quantity),
                )
        
        # Submit the operation
        submitted_operation = await uow.operations.submit_operation(
            operation_id=operation_id,
            submitted_by_user_id=user_id,
        )
        
        logger.info(
            f"Submitted operation {operation.operation_uuid} "
            f"by user {user_id}"
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
        
        # Check if user can cancel this operation
        if not await OperationsService.validate_operation_permissions(
            uow, user_id, operation.site_id, "storekeeper"
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have permission to cancel this operation",
            )
        
        # Check operation status
        if operation.status == "cancelled":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Operation is already cancelled",
            )
        
        # Reverse balance changes if operation was submitted
        if operation.status == "submitted":
            for line in operation.lines:
                if operation.type == "RECEIVE":
                    # Reverse: decrease balance
                    await uow.balances.update_balance_quantity(
                        site_id=operation.site_id,
                        item_id=line.item_id,
                        quantity_delta=Decimal(-line.quantity),
                    )
                elif operation.type == "WRITE_OFF":
                    # Reverse: increase balance
                    await uow.balances.update_balance_quantity(
                        site_id=operation.site_id,
                        item_id=line.item_id,
                        quantity_delta=Decimal(line.quantity),
                    )
                elif operation.type == "MOVE":
                    if line.source_site_id and line.target_site_id:
                        # Reverse: increase at source, decrease at target
                        await uow.balances.update_balance_quantity(
                            site_id=line.source_site_id,
                            item_id=line.item_id,
                            quantity_delta=Decimal(line.quantity),
                        )
                        await uow.balances.update_balance_quantity(
                            site_id=line.target_site_id,
                            item_id=line.item_id,
                            quantity_delta=Decimal(-line.quantity),
                        )
                elif operation.type == "ISSUE":
                    # Reverse: increase balance
                    await uow.balances.update_balance_quantity(
                        site_id=operation.site_id,
                        item_id=line.item_id,
                        quantity_delta=Decimal(line.quantity),
                    )
        
        # Cancel the operation
        cancelled_operation = await uow.operations.cancel_operation(
            operation_id=operation_id,
            cancelled_by_user_id=user_id,
        )
        
        logger.info(
            f"Cancelled operation {operation.operation_uuid} "
            f"by user {user_id}, reason: {reason}"
        )
        
        return {"operation": cancelled_operation}