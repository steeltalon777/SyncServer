from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.operation import Operation, OperationLine
from app.schemas.operation import OperationFilter


class OperationsRepo:
    """Repository for operations and operation lines."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_operation(
        self,
        operation_uuid: UUID,
        site_id: UUID,
        type: Literal["RECEIVE", "WRITE_OFF", "MOVE", "ISSUE"],
        created_by_user_id: int,
        notes: str | None = None,
    ) -> Operation:
        """Create a new operation."""
        operation = Operation(
            operation_uuid=operation_uuid,
            site_id=site_id,
            type=type,
            status="draft",
            created_by_user_id=created_by_user_id,
            notes=notes,
        )
        self.session.add(operation)
        await self.session.flush()
        return operation

    async def get_operation_by_id(self, operation_id: int) -> Operation | None:
        """Get operation by ID with lines."""
        stmt = (
            select(Operation)
            .where(Operation.id == operation_id)
            .options(selectinload(Operation.lines))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_operation_by_uuid(self, operation_uuid: UUID) -> Operation | None:
        """Get operation by UUID with lines."""
        stmt = (
            select(Operation)
            .where(Operation.operation_uuid == operation_uuid)
            .options(selectinload(Operation.lines))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_operation(
        self,
        operation_id: int,
        notes: str | None = None,
    ) -> Operation | None:
        """Update operation notes."""
        operation = await self.get_operation_by_id(operation_id)
        if operation:
            if notes is not None:
                operation.notes = notes
            await self.session.flush()
        return operation

    async def submit_operation(
        self,
        operation_id: int,
        submitted_by_user_id: int,
        submitted_at: datetime | None = None,
    ) -> Operation | None:
        """Submit an operation."""
        operation = await self.get_operation_by_id(operation_id)
        if operation and operation.status == "draft":
            operation.status = "submitted"
            operation.submitted_by_user_id = submitted_by_user_id
            operation.submitted_at = submitted_at or datetime.utcnow()
            await self.session.flush()
        return operation

    async def cancel_operation(
        self,
        operation_id: int,
        cancelled_by_user_id: int,
        cancelled_at: datetime | None = None,
    ) -> Operation | None:
        """Cancel an operation."""
        operation = await self.get_operation_by_id(operation_id)
        if operation and operation.status in ["draft", "submitted"]:
            operation.status = "cancelled"
            operation.cancelled_by_user_id = cancelled_by_user_id
            operation.cancelled_at = cancelled_at or datetime.utcnow()
            await self.session.flush()
        return operation

    async def list_operations(
        self,
        filter: OperationFilter,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Operation], int]:
        """List operations with filtering and pagination."""
        # Build query
        stmt = select(Operation).options(selectinload(Operation.lines))
        where_clauses = []
        
        if filter.site_id:
            where_clauses.append(Operation.site_id == filter.site_id)
        if filter.type:
            where_clauses.append(Operation.type == filter.type)
        if filter.status:
            where_clauses.append(Operation.status == filter.status)
        if filter.created_by_user_id:
            where_clauses.append(Operation.created_by_user_id == filter.created_by_user_id)
        if filter.created_after:
            where_clauses.append(Operation.created_at >= filter.created_after)
        if filter.created_before:
            where_clauses.append(Operation.created_at <= filter.created_before)
        if filter.updated_after:
            where_clauses.append(Operation.updated_at >= filter.updated_after)
        if filter.updated_before:
            where_clauses.append(Operation.updated_at <= filter.updated_before)
        if filter.search:
            search_term = f"%{filter.search}%"
            where_clauses.append(
                or_(
                    Operation.notes.ilike(search_term),
                )
            )
        
        if where_clauses:
            stmt = stmt.where(and_(*where_clauses))
        
        # Count total
        count_stmt = select(func.count()).select_from(Operation)
        if where_clauses:
            count_stmt = count_stmt.where(and_(*where_clauses))
        total_result = await self.session.execute(count_stmt)
        total_count = total_result.scalar_one()
        
        # Apply pagination and ordering
        stmt = stmt.order_by(desc(Operation.created_at))
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        
        result = await self.session.execute(stmt)
        operations = list(result.scalars().all())
        
        return operations, total_count

    async def create_operation_line(
        self,
        operation_id: int,
        line_number: int,
        item_id: int,
        quantity: int,
        source_site_id: UUID | None = None,
        target_site_id: UUID | None = None,
        notes: str | None = None,
    ) -> OperationLine:
        """Create an operation line."""
        line = OperationLine(
            operation_id=operation_id,
            line_number=line_number,
            item_id=item_id,
            quantity=quantity,
            source_site_id=source_site_id,
            target_site_id=target_site_id,
            notes=notes,
        )
        self.session.add(line)
        await self.session.flush()
        return line

    async def delete_operation_lines(self, operation_id: int) -> None:
        """Delete all lines for an operation."""
        stmt = select(OperationLine).where(OperationLine.operation_id == operation_id)
        result = await self.session.execute(stmt)
        lines = result.scalars().all()
        for line in lines:
            await self.session.delete(line)
        await self.session.flush()

    async def get_operation_lines(self, operation_id: int) -> list[OperationLine]:
        """Get all lines for an operation."""
        stmt = select(OperationLine).where(OperationLine.operation_id == operation_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def user_has_access_to_operation(
        self,
        user_id: int,
        operation_id: int,
        user_site_roles: list[tuple[UUID, str]],
    ) -> bool:
        """Check if user has access to an operation."""
        operation = await self.get_operation_by_id(operation_id)
        if not operation:
            return False
        
        # Check if user created the operation
        if operation.created_by_user_id == user_id:
            return True
        
        # Check user's roles for the operation's site
        user_sites = {site_id for site_id, _ in user_site_roles}
        return operation.site_id in user_sites