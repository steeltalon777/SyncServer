from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.operation import OperationCorrection, OperationCorrectionLine


class CorrectionsRepo:
    """Repository for OperationCorrection and OperationCorrectionLine.

    Features:
    - version + expected_version for optimistic locking
    - idempotency_key for retry safety
    - Partial unique index: одна active draft на operation
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # ─── Correction CRUD ──────────────────────────────────────────────

    async def create_correction(
        self,
        operation_id: UUID,
        base_operation_revision_id: UUID,
        created_by_user_id: UUID,
        idempotency_key: str | None = None,
    ) -> OperationCorrection:
        correction = OperationCorrection(
            operation_id=operation_id,
            status="draft",
            base_operation_revision_id=base_operation_revision_id,
            version=1,
            idempotency_key=idempotency_key,
            created_by_user_id=created_by_user_id,
        )
        self.session.add(correction)
        await self.session.flush()
        return correction

    async def get_correction_by_id(
        self, correction_id: UUID,
    ) -> OperationCorrection | None:
        stmt = (
            select(OperationCorrection)
            .where(OperationCorrection.id == correction_id)
            .options(selectinload(OperationCorrection.lines))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_correction_by_id_for_update(
        self, correction_id: UUID,
    ) -> OperationCorrection | None:
        stmt = (
            select(OperationCorrection)
            .where(OperationCorrection.id == correction_id)
            .with_for_update()
            .options(selectinload(OperationCorrection.lines))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_active_draft_for_operation(
        self, operation_id: UUID,
    ) -> OperationCorrection | None:
        stmt = (
            select(OperationCorrection)
            .where(OperationCorrection.operation_id == operation_id)
            .where(OperationCorrection.status == "draft")
            .options(selectinload(OperationCorrection.lines))
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def update_correction_status(
        self,
        correction_id: UUID,
        status: str,
        expected_version: int | None = None,
        submitted_by_user_id: UUID | None = None,
    ) -> OperationCorrection | None:
        correction = await self.get_correction_by_id_for_update(correction_id)
        if correction is None:
            return None

        if expected_version is not None and int(correction.version) != expected_version:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "correction_version_conflict",
                    "current_version": int(correction.version),
                },
            )

        correction.status = status
        correction.version = int(correction.version) + 1

        if status == "applied":
            correction.applied_at = datetime.now(UTC)
            correction.submitted_at = correction.submitted_at or datetime.now(UTC)
            correction.submitted_by_user_id = correction.submitted_by_user_id or submitted_by_user_id
        elif status == "abandoned":
            pass  # no extra timestamps needed
        elif status == "draft":
            correction.updated_at = datetime.now(UTC)

        await self.session.flush()
        return correction

    # ─── Correction Line CRUD ─────────────────────────────────────────

    async def create_correction_line(
        self,
        correction_id: UUID,
        line_uuid: UUID,
        line_number: int,
        item_id: int | None,
        qty: Decimal,
        batch: str | None = None,
        comment: str | None = None,
    ) -> OperationCorrectionLine:
        line = OperationCorrectionLine(
            correction_id=correction_id,
            line_uuid=line_uuid,
            line_number=line_number,
            item_id=item_id,
            qty=qty,
            batch=batch,
            comment=comment,
        )
        self.session.add(line)
        await self.session.flush()
        return line

    async def replace_all_lines(
        self,
        correction_id: UUID,
        lines: list[dict],
    ) -> list[OperationCorrectionLine]:
        """Replace all lines in a correction (PUT full target state).

        Deletes existing lines and inserts new ones in the same UoW.
        """
        correction = await self.get_correction_by_id_for_update(correction_id)
        if correction is None:
            return []

        # Delete existing lines
        existing = await self.get_correction_lines(correction_id)
        for line in existing:
            await self.session.delete(line)
        await self.session.flush()

        # Insert new lines
        result = []
        for line_data in lines:
            line = await self.create_correction_line(
                correction_id=correction_id,
                line_uuid=line_data["line_uuid"],
                line_number=line_data["line_number"],
                item_id=line_data["item_id"],
                qty=line_data["qty"],
                batch=line_data.get("batch"),
                comment=line_data.get("comment"),
            )
            result.append(line)
        return result

    async def get_correction_lines(
        self, correction_id: UUID,
    ) -> list[OperationCorrectionLine]:
        stmt = (
            select(OperationCorrectionLine)
            .where(OperationCorrectionLine.correction_id == correction_id)
            .order_by(OperationCorrectionLine.line_number)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_correction_line_by_uuid(
        self, correction_id: UUID, line_uuid: UUID,
    ) -> OperationCorrectionLine | None:
        stmt = (
            select(OperationCorrectionLine)
            .where(OperationCorrectionLine.correction_id == correction_id)
            .where(OperationCorrectionLine.line_uuid == line_uuid)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def delete_correction_line(
        self, correction_id: UUID, line_uuid: UUID,
    ) -> bool:
        line = await self.get_correction_line_by_uuid(correction_id, line_uuid)
        if line is None:
            return False
        await self.session.delete(line)
        await self.session.flush()
        return True

    async def get_correction_by_idempotency_key(
        self, operation_id: UUID, idempotency_key: str,
    ) -> OperationCorrection | None:
        stmt = (
            select(OperationCorrection)
            .where(OperationCorrection.operation_id == operation_id)
            .where(OperationCorrection.idempotency_key == idempotency_key)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
