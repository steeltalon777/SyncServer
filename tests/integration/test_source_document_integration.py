"""Integration tests for source-document operation pipeline.

Covers 6 scenarios from TZ §11.2 (Gate A1 + A2).
Requires a running dev stand with seeded data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import HTTPException, status
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


async def _find_any_item(session):
    stmt = select(Item).where(Item.is_active.is_(True)).where(Item.deleted_at.is_(None)).limit(1)
    result = await session.execute(stmt)
    item = result.scalar_one_or_none()
    if item is None:
        pytest.skip("No active catalog items in seed data")
    return item.id


@pytest.mark.integration
async def test_scenario_1_source_document_resolved_items():
    """Сценарий 1: Source-document со всеми resolved items."""
    async with SessionFactory() as session:
        item_id = await _find_any_item(session)
        user_id = _test_user_id()
        source_ref = f"int-test-{uuid4().hex[:8]}"

        payload = SourceDocumentOperationCreate(
            operation_type="RECEIVE",
            site_id=1,
            source_ref=source_ref,
            source_document_type="invoice",
            effective_at=datetime.now(UTC),
            client_request_id=f"client-{source_ref}",
            lines=[
                SourceDocumentOperationLineCreate(
                    line_number=1, item_id=item_id, qty=Decimal("10"),
                    source_item_name="Test Source Item",
                    source_item_sku="TEST-SRC-001",
                ),
            ],
        )

        uow = UnitOfWork(session)
        result = await OperationsService.create_operation_from_source_document(
            uow=uow, payload=payload, user_id=user_id,
        )
        op = result["operation"]

        assert op.creation_source == "source_document"
        assert op.source_ref == source_ref
        assert op.status == "draft"
        assert len(op.lines) == 1
        assert op.lines[0].item_id == item_id
        assert op.lines[0].source_item_name == "Test Source Item"
        assert op.lines[0].source_item_sku == "TEST-SRC-001"
        assert op.lines[0].temporary_draft_payload is None
        assert op.lines[0].resolution_mode == "existing_item"
        await session.commit()


@pytest.mark.integration
async def test_scenario_2_unresolved_line_422_on_create():
    """Сценарий 2: Source-document с несуществующим item_id → 422 на create."""
    async with SessionFactory() as session:
        user_id = _test_user_id()

        payload = SourceDocumentOperationCreate(
            operation_type="RECEIVE",
            site_id=1,
            source_ref=f"int-test-unresolved-{uuid4().hex[:8]}",
            source_document_type="invoice",
            effective_at=datetime.now(UTC),
            lines=[
                SourceDocumentOperationLineCreate(
                    line_number=1, item_id=99999999, qty=Decimal("10"),
                ),
            ],
        )

        uow = UnitOfWork(session)
        with pytest.raises(HTTPException) as exc_info:
            await OperationsService.create_operation_from_source_document(
                uow=uow, payload=payload, user_id=user_id,
            )

        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        detail = exc_info.value.detail
        if isinstance(detail, dict):
            assert "source_document_line_unresolvable" in detail.get("code", "")


@pytest.mark.integration
async def test_scenario_3_temporary_item_rejected():
    """Сценарий 3: Попытка передать unknown field — extra='forbid'."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SourceDocumentOperationLineCreate(
            line_number=1, item_id=100, qty=Decimal("10"),
            unknown_field="test",
        )


@pytest.mark.integration
async def test_scenario_4_submit_no_item_creation():
    """Сценарий 4: Submit source_document не создаёт Item."""
    async with SessionFactory() as session:
        item_id = await _find_any_item(session)
        user_id = _test_user_id()
        source_ref = f"int-test-submit-{uuid4().hex[:8]}"

        payload = SourceDocumentOperationCreate(
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

        uow = UnitOfWork(session)
        result = await OperationsService.create_operation_from_source_document(
            uow=uow, payload=payload, user_id=user_id,
        )
        op = result["operation"]

        # Submit
        result = await OperationsService.submit_operation(
            uow=uow, operation_id=op.id, user_id=user_id,
        )
        submitted = result["operation"]
        assert submitted.status == "submitted"

        # Verify no NEW items were created with source_system='operation_inline'
        # (there may be pre-existing ones from seed data)
        from app.models.item import Item
        stmt = select(Item).where(
            Item.source_system == "operation_inline",
            Item.source_ref == f"client-{source_ref}",
        )
        items = (await session.execute(stmt)).scalars().all()
        assert len(items) == 0, \
            f"Found {len(items)} operation_inline items after source_document submit"

        await session.commit()


@pytest.mark.integration
async def test_scenario_5_rename_item_between_create_and_submit():
    """Сценарий 5: Rename Item между create и submit.
    Snapshot обновляется на submit.
    """
    async with SessionFactory() as session:
        item_id = await _find_any_item(session)
        user_id = _test_user_id()
        source_ref = f"int-test-rename-{uuid4().hex[:8]}"

        item = await session.get(Item, item_id)
        original_name = item.name

        payload = SourceDocumentOperationCreate(
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

        uow = UnitOfWork(session)
        try:
            result = await OperationsService.create_operation_from_source_document(
                uow=uow, payload=payload, user_id=user_id,
            )
            op = result["operation"]

            # Rename item between create and submit
            new_name = f"{original_name} (RENAMED {datetime.now(UTC).isoformat()})"
            item.name = new_name
            await session.flush()

            await OperationsService.submit_operation(
                uow=uow, operation_id=op.id, user_id=user_id,
            )

            fresh_op = await uow.operations.get_operation_by_id(op.id)
            line = fresh_op.lines[0]

            assert line.item_name_snapshot == new_name, \
                f"Expected '{new_name}', got '{line.item_name_snapshot}'"
            await session.commit()
        finally:
            # Restore the shared item's name so this test does not pollute the
            # persistent DB. Rollback first: on the failure path this releases
            # the uncommitted rename lock held by this session (no-op after a
            # successful commit). Then restore the original name in a fresh
            # session. Runs even when the assertion above fails.
            await session.rollback()
            async with SessionFactory() as restore_session:
                item_to_restore = await restore_session.get(Item, item_id)
                if item_to_restore is not None:
                    item_to_restore.name = original_name
                    await restore_session.commit()


@pytest.mark.integration
async def test_scenario_6_merge_item_between_create_and_submit():
    """Сценарий 6: Merge Item между create и submit.
    Snapshot обновляется на canonical.
    """
    async with SessionFactory() as session:
        stmt = select(Item).where(Item.is_active.is_(True)).where(Item.deleted_at.is_(None)).limit(2)
        items = (await session.execute(stmt)).scalars().all()
        if len(items) < 2:
            pytest.skip("Need >=2 active items")

        source_item, target_item = items[0], items[1]
        user_id = _test_user_id()
        source_ref = f"merge-test-{uuid4().hex[:8]}"

        payload = SourceDocumentOperationCreate(
            operation_type="RECEIVE",
            site_id=1,
            source_ref=source_ref,
            source_document_type="invoice",
            effective_at=datetime.now(UTC),
            client_request_id=f"client-{source_ref}",
            lines=[
                SourceDocumentOperationLineCreate(
                    line_number=1, item_id=source_item.id, qty=Decimal("10"),
                ),
            ],
        )

        uow = UnitOfWork(session)
        result = await OperationsService.create_operation_from_source_document(
            uow=uow, payload=payload, user_id=user_id,
        )
        op = result["operation"]

        # Simulate merge
        source_item.merged_into_id = target_item.id
        await session.flush()

        await OperationsService.submit_operation(
            uow=uow, operation_id=op.id, user_id=user_id,
        )

        fresh_op = await uow.operations.get_operation_by_id(op.id)
        line = fresh_op.lines[0]

        assert line.item_id == target_item.id, \
            f"Expected canonical item_id={target_item.id}, got {line.item_id}"
        assert line.item_name_snapshot == target_item.name

        # Cleanup
        source_item.merged_into_id = None
        await session.commit()
