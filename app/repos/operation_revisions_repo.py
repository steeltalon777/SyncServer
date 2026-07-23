from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.operation import OperationRevision, OperationRevisionLine


class OperationRevisionsRepo:
    """Repository for immutable OperationRevision and OperationRevisionLine.

    INV-C1: OperationRevision и OperationRevisionLine immutable после создания.
    Update запрещён на уровне repo (raise NotImplementedError).
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_revision(
        self,
        operation_id: UUID,
        revision_number: int,
        created_by_user_id: UUID,
        created_by_correction_id: UUID | None = None,
    ) -> OperationRevision:
        revision = OperationRevision(
            operation_id=operation_id,
            revision_number=revision_number,
            created_by_user_id=created_by_user_id,
            created_by_correction_id=created_by_correction_id,
        )
        self.session.add(revision)
        await self.session.flush()
        return revision

    async def get_revision_by_id(
        self, revision_id: UUID,
    ) -> OperationRevision | None:
        stmt = (
            select(OperationRevision)
            .where(OperationRevision.id == revision_id)
            .options(selectinload(OperationRevision.lines))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_revision_by_id_for_update(
        self, revision_id: UUID,
    ) -> OperationRevision | None:
        stmt = (
            select(OperationRevision)
            .where(OperationRevision.id == revision_id)
            .with_for_update()
            .options(selectinload(OperationRevision.lines))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_revisions_for_operation(
        self, operation_id: UUID,
    ) -> list[OperationRevision]:
        stmt = (
            select(OperationRevision)
            .where(OperationRevision.operation_id == operation_id)
            .order_by(OperationRevision.revision_number)
            .options(selectinload(OperationRevision.lines))
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_latest_revision_for_operation(
        self, operation_id: UUID,
    ) -> OperationRevision | None:
        stmt = (
            select(OperationRevision)
            .where(OperationRevision.operation_id == operation_id)
            .order_by(OperationRevision.revision_number.desc())
            .options(selectinload(OperationRevision.lines))
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create_revision_line(
        self,
        revision_id: UUID,
        line_uuid: UUID,
        line_number: int,
        item_id: int | None,
        inventory_subject_id: int | None,
        qty: Decimal,
        accepted_qty: Decimal = Decimal("0"),
        lost_qty: Decimal = Decimal("0"),
        batch: str | None = None,
        comment: str | None = None,
        source_item_name: str | None = None,
        source_item_sku: str | None = None,
        source_unit_name: str | None = None,
        source_category_name: str | None = None,
        item_name_snapshot: str | None = None,
        item_sku_snapshot: str | None = None,
        unit_name_snapshot: str | None = None,
        unit_symbol_snapshot: str | None = None,
        category_name_snapshot: str | None = None,
    ) -> OperationRevisionLine:
        line = OperationRevisionLine(
            revision_id=revision_id,
            line_uuid=line_uuid,
            line_number=line_number,
            item_id=item_id,
            inventory_subject_id=inventory_subject_id,
            qty=qty,
            accepted_qty=accepted_qty,
            lost_qty=lost_qty,
            batch=batch,
            comment=comment,
            source_item_name=source_item_name,
            source_item_sku=source_item_sku,
            source_unit_name=source_unit_name,
            source_category_name=source_category_name,
            item_name_snapshot=item_name_snapshot,
            item_sku_snapshot=item_sku_snapshot,
            unit_name_snapshot=unit_name_snapshot,
            unit_symbol_snapshot=unit_symbol_snapshot,
            category_name_snapshot=category_name_snapshot,
        )
        self.session.add(line)
        await self.session.flush()
        return line

    async def update(self, *args, **kwargs):
        raise NotImplementedError("OperationRevision is immutable")

    async def delete(self, revision_id: UUID) -> None:
        revision = await self.get_revision_by_id(revision_id)
        if revision is not None:
            await self.session.delete(revision)
            await self.session.flush()
