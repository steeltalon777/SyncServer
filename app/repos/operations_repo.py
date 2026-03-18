from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
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
        site_id: int,
        operation_type: Literal["RECEIVE", "WRITE_OFF", "MOVE"],
        created_by_user_id: UUID,
        notes: str | None = None,
        source_site_id: int | None = None,
        destination_site_id: int | None = None,
        issued_to_user_id: UUID | None = None,
        issued_to_name: str | None = None,
    ) -> Operation:
        operation = Operation(
            site_id=site_id,
            operation_type=operation_type,
            status="draft",
            source_site_id=source_site_id,
            destination_site_id=destination_site_id,
            issued_to_user_id=issued_to_user_id,
            issued_to_name=issued_to_name,
            created_by_user_id=created_by_user_id,
            notes=notes,
        )
        self.session.add(operation)
        await self.session.flush()
        return operation

    async def get_operation_by_id(self, operation_id: UUID) -> Operation | None:
        stmt = (
            select(Operation)
            .where(Operation.id == operation_id)
            .options(selectinload(Operation.lines))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_operation(
        self,
        operation_id: UUID,
        *,
        notes: str | None = None,
        source_site_id: int | None = None,
        destination_site_id: int | None = None,
        issued_to_user_id: UUID | None = None,
        issued_to_name: str | None = None,
        fields_set: set[str] | None = None,
    ) -> Operation | None:
        operation = await self.get_operation_by_id(operation_id)
        if operation is None:
            return None

        if notes is not None:
            operation.notes = notes
        if fields_set is not None and "source_site_id" in fields_set:
            operation.source_site_id = source_site_id
        if fields_set is not None and "destination_site_id" in fields_set:
            operation.destination_site_id = destination_site_id
        if fields_set is not None and "issued_to_user_id" in fields_set:
            operation.issued_to_user_id = issued_to_user_id
        if fields_set is not None and "issued_to_name" in fields_set:
            operation.issued_to_name = issued_to_name

        await self.session.flush()
        return operation

    async def submit_operation(
        self,
        operation_id: UUID,
        submitted_by_user_id: UUID,
        submitted_at: datetime | None = None,
    ) -> Operation | None:
        operation = await self.get_operation_by_id(operation_id)
        if operation and operation.status == "draft":
            operation.status = "submitted"
            operation.submitted_by_user_id = submitted_by_user_id
            operation.submitted_at = submitted_at or datetime.now(UTC)
            await self.session.flush()
        return await self.get_operation_by_id(operation_id)
        return operation

    async def cancel_operation(
        self,
        operation_id: UUID,
        cancelled_by_user_id: UUID,
        cancelled_at: datetime | None = None,
    ) -> Operation | None:
        operation = await self.get_operation_by_id(operation_id)
        if operation and operation.status in ["draft", "submitted"]:
            operation.status = "cancelled"
            operation.cancelled_by_user_id = cancelled_by_user_id
            operation.cancelled_at = cancelled_at or datetime.now(UTC)
            await self.session.flush()
        return await self.get_operation_by_id(operation_id)
        return operation

    async def list_operations(
        self,
        filter: OperationFilter,
        user_site_ids: list[int],
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Operation], int]:
        stmt = select(Operation).options(selectinload(Operation.lines))
        where_clauses = []

        if user_site_ids:
            where_clauses.append(Operation.site_id.in_(user_site_ids))
        else:
            where_clauses.append(False)

        if filter.site_id is not None:
            where_clauses.append(Operation.site_id == filter.site_id)
        if filter.type is not None:
            where_clauses.append(Operation.operation_type == filter.type)
        if filter.status is not None:
            where_clauses.append(Operation.status == filter.status)
        if filter.created_by_user_id is not None:
            where_clauses.append(
                Operation.created_by_user_id == filter.created_by_user_id
            )
        if filter.created_after is not None:
            where_clauses.append(Operation.created_at >= filter.created_after)
        if filter.created_before is not None:
            where_clauses.append(Operation.created_at <= filter.created_before)
        if filter.updated_after is not None:
            where_clauses.append(Operation.updated_at >= filter.updated_after)
        if filter.updated_before is not None:
            where_clauses.append(Operation.updated_at <= filter.updated_before)
        if filter.search:
            term = f"%{filter.search}%"
            where_clauses.append(or_(Operation.notes.ilike(term)))

        stmt = stmt.where(and_(*where_clauses))
        count_stmt = (
            select(func.count()).select_from(Operation).where(and_(*where_clauses))
        )

        total_count = (await self.session.execute(count_stmt)).scalar_one()
        stmt = (
            stmt.order_by(desc(Operation.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        operations = list((await self.session.execute(stmt)).scalars().all())
        return operations, total_count

    async def create_operation_line(
        self,
        operation_id: UUID,
        line_number: int,
        item_id: int,
        qty: Decimal | int,
        batch: str | None = None,
        comment: str | None = None,
    ) -> OperationLine:
        line = OperationLine(
            operation_id=operation_id,
            line_number=line_number,
            item_id=item_id,
            qty=qty,
            batch=batch,
            comment=comment,
        )
        self.session.add(line)
        await self.session.flush()
        return line

    async def delete_operation_lines(self, operation_id: UUID) -> None:
        stmt = select(OperationLine).where(OperationLine.operation_id == operation_id)
        lines = (await self.session.execute(stmt)).scalars().all()
        for line in lines:
            await self.session.delete(line)
        await self.session.flush()
