"""Integration test: source-document idempotency.

N-5: повторная отправка того же source_ref возвращает ту же операцию.
W-5: разный payload с тем же source_ref → 409.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import HTTPException
import pytest

from app.core.db import SessionFactory
from app.models.item import Item
from app.schemas.operation import (
    SourceDocumentOperationCreate,
    SourceDocumentOperationLineCreate,
)
from app.services.operations_service import OperationsService
from app.services.uow import UnitOfWork
from sqlalchemy import select


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration,
]


def _test_user_id() -> UUID:
    # Svetlana (chief_storekeeper, default_site_id=1)
    return UUID("7337709e-a82b-4813-8b4d-283addc7a9c3")


async def _find_any_item(session) -> int:
    stmt = select(Item).where(Item.is_active.is_(True)).where(Item.deleted_at.is_(None)).limit(1)
    result = await session.execute(stmt)
    item = result.scalar_one_or_none()
    if item is None:
        pytest.skip("No active catalog items")
    return item.id


@pytest.mark.integration
async def test_repeat_same_source_ref_returns_same_operation():
    """Повторная отправка source_document с тем же source_ref
    и тем же payload возвращает ту же Operation."""
    async with SessionFactory() as session:
        item_id = await _find_any_item(session)
        user_id = _test_user_id()
        source_ref = f"idem-test-{uuid4().hex[:8]}"
        fixed_date = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)

        # Первая отправка
        payload_1 = SourceDocumentOperationCreate(
            operation_type="RECEIVE",
            site_id=1,
            source_ref=source_ref,
            source_document_type="invoice",
            effective_at=fixed_date,
            client_request_id=f"client-{source_ref}",
            lines=[
                SourceDocumentOperationLineCreate(
                    line_number=1, item_id=item_id, qty=Decimal("10"),
                ),
            ],
        )
        uow_1 = UnitOfWork(session)
        result_1 = await OperationsService.create_operation_from_source_document(
            uow=uow_1, payload=payload_1, user_id=user_id,
        )
        op_1 = result_1["operation"]
        op_1_id = op_1.id

        # Вторая отправка с тем же source_ref и тем же payload
        payload_2 = SourceDocumentOperationCreate(
            operation_type="RECEIVE",
            site_id=1,
            source_ref=source_ref,
            source_document_type="invoice",
            effective_at=fixed_date,
            client_request_id=f"client-{source_ref}",
            lines=[
                SourceDocumentOperationLineCreate(
                    line_number=1, item_id=item_id, qty=Decimal("10"),
                ),
            ],
        )
        uow_2 = UnitOfWork(session)
        result_2 = await OperationsService.create_operation_from_source_document(
            uow=uow_2, payload=payload_2, user_id=user_id,
        )
        op_2 = result_2["operation"]

        assert op_2.id == op_1_id, \
            f"Expected same operation ID, got {op_2.id} != {op_1_id}"
        assert op_2.creation_source == "source_document"


@pytest.mark.integration
async def test_different_payload_same_source_ref_returns_409():
    """Разный payload с тем же source_ref → 409 conflict."""
    async with SessionFactory() as session:
        item_id = await _find_any_item(session)
        user_id = _test_user_id()
        source_ref = f"conflict-test-{uuid4().hex[:8]}"

        # Первая отправка
        payload_1 = SourceDocumentOperationCreate(
            operation_type="RECEIVE",
            site_id=1,
            source_ref=source_ref,
            source_document_type="invoice",
            effective_at=datetime.now(UTC),
            client_request_id=f"client-{source_ref}",
            lines=[
                SourceDocumentOperationLineCreate(
                    line_number=1, item_id=item_id, qty=Decimal("10"),
                ),
            ],
        )
        uow_1 = UnitOfWork(session)
        await OperationsService.create_operation_from_source_document(
            uow=uow_1, payload=payload_1, user_id=user_id,
        )

        # Вторая отправка с другим payload
        payload_2 = SourceDocumentOperationCreate(
            operation_type="RECEIVE",
            site_id=1,
            source_ref=source_ref,  # тот же source_ref
            source_document_type="invoice",
            effective_at=datetime.now(UTC),
            client_request_id=f"client-{source_ref}",
            lines=[
                SourceDocumentOperationLineCreate(
                    line_number=1, item_id=item_id, qty=Decimal("20"),  # другое qty
                ),
            ],
        )
        uow_2 = UnitOfWork(session)
        with pytest.raises(HTTPException) as exc_info:
            await OperationsService.create_operation_from_source_document(
                uow=uow_2, payload=payload_2, user_id=user_id,
            )

        assert exc_info.value.status_code == 409
        detail = exc_info.value.detail
        if isinstance(detail, dict):
            assert "source_document_idempotency_conflict" in detail.get("code", "")
