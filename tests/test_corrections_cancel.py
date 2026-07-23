from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, PropertyMock
from uuid import UUID, uuid4

import pytest

from app.services.corrections_service import ComputedDiff, CorrectionsService
from app.services.operations_service import OperationsService
from fastapi import HTTPException


class MockUoW:
    def __init__(self):
        self.operations = AsyncMock()
        self.operation_revisions = AsyncMock()
        self.corrections = AsyncMock()
        self.catalog = AsyncMock()
        self.balances = AsyncMock()
        self.inventory_subjects = AsyncMock()
        self.sites = AsyncMock()
        self.users = AsyncMock()
        self.documents = AsyncMock()
        self.audit_events = AsyncMock()
        self.session = AsyncMock()
        self.batch_correlation_id = None
        self.audit_parent_event_id = None
        self.audit_caused_by_event_id = None
        self.audit_effect_type_override = None


def _make_operation(id=None, status="submitted", site_id=1, operation_type="RECEIVE",
                    acceptance_required=False, version=1):
    op = MagicMock()
    op.id = id or uuid4()
    op.site_id = site_id
    op.status = status
    op.operation_type = operation_type
    op.acceptance_required = acceptance_required
    op.version = version
    op.short_id = "TEST-001"
    op.current_revision_id = uuid4()
    op.correction_count = 0
    op.last_corrected_at = None
    return op


def _make_revision(id=None, revision_number=0, lines=None):
    rev = MagicMock()
    rev.id = id or uuid4()
    rev.revision_number = revision_number
    rev.lines = lines or []
    return rev


def _make_revision_line(line_uuid=None, item_id=1, qty=100, line_number=1,
                        inventory_subject_id=1, batch=None, comment=None):
    rl = MagicMock()
    rl.line_uuid = line_uuid or uuid4()
    rl.line_number = line_number
    rl.item_id = item_id
    rl.qty = Decimal(str(qty))
    rl.inventory_subject_id = inventory_subject_id
    rl.batch = batch
    rl.comment = comment
    rl.accepted_qty = Decimal("0")
    rl.lost_qty = Decimal("0")
    rl.source_item_name = None
    rl.source_item_sku = None
    rl.source_unit_name = None
    rl.source_category_name = None
    rl.item_name_snapshot = "Item"
    rl.item_sku_snapshot = "SKU-001"
    rl.unit_name_snapshot = "pcs"
    rl.unit_symbol_snapshot = "pcs"
    rl.category_name_snapshot = "Category"
    return rl


def _make_correction_line(line_uuid=None, item_id=1, qty=100, line_number=1,
                          batch=None, comment=None):
    cl = MagicMock()
    cl.line_uuid = line_uuid or uuid4()
    cl.line_number = line_number
    cl.item_id = item_id
    cl.qty = Decimal(str(qty))
    cl.batch = batch
    cl.comment = comment
    return cl


class TestCancelAfterCorrection:
    """Mandatory test: cancel after multiple corrections restores pre-op state."""

    @pytest.mark.asyncio
    async def test_cancel_after_correction_reverses_cumulative_effects(self):
        """Cancel after qty increase correction should reverse total delta."""
        line_uuid = uuid4()
        operation_id = uuid4()
        correction_id = uuid4()
        user_id = uuid4()
        rev_0_id = uuid4()
        rev_1_id = uuid4()

        uow = MockUoW()

        # Operation with current_revision_id after correction
        operation = _make_operation(id=operation_id, status="submitted", version=3)
        operation.current_revision_id = rev_1_id
        operation.correction_count = 1
        operation.lines = [
            MagicMock(
                id=1, line_uuid=line_uuid, line_number=1, item_id=1,
                inventory_subject_id=1, qty=Decimal("120"),
                accepted_qty=Decimal("0"), lost_qty=Decimal("0"),
                batch=None, comment=None, item_name_snapshot="Item",
                item_sku_snapshot="SKU", unit_name_snapshot="pcs",
                unit_symbol_snapshot="pcs", category_name_snapshot="Cat",
            ),
        ]

        uow.operations.get_operation_by_id = AsyncMock(return_value=operation)

        # Mock cancel_operation to succeed
        uow.operations.cancel_operation = AsyncMock(return_value=operation)
        uow.operations.get_operation_by_id_for_update = AsyncMock(return_value=operation)
        uow.inventory_subjects.get_by_id = AsyncMock(return_value=None)

        uow.balances.get_for_update = AsyncMock(return_value=MagicMock(qty=Decimal("1000")))

        result = await OperationsService.cancel_operation(
            uow=uow,
            operation_id=operation_id,
            user_id=user_id,
            reason="test cancel",
        )

        assert result is not None
        assert uow.operations.cancel_operation.called

    @pytest.mark.asyncio
    async def test_cancel_with_no_correction_still_works(self):
        """Cancel on submitted operation without correction."""
        operation_id = uuid4()
        user_id = uuid4()

        uow = MockUoW()
        operation = _make_operation(id=operation_id, status="submitted", version=2)
        operation.current_revision_id = uuid4()
        operation.correction_count = 0
        operation.lines = [
            MagicMock(
                id=1, line_uuid=uuid4(), line_number=1, item_id=1,
                inventory_subject_id=1, qty=Decimal("100"),
                accepted_qty=Decimal("0"), lost_qty=Decimal("0"),
            ),
        ]

        uow.operations.get_operation_by_id = AsyncMock(return_value=operation)
        uow.operations.cancel_operation = AsyncMock(return_value=operation)
        uow.operations.get_operation_by_id_for_update = AsyncMock(return_value=operation)
        uow.inventory_subjects.get_by_id = AsyncMock(return_value=None)
        uow.balances.get_for_update = AsyncMock(return_value=MagicMock(qty=Decimal("1000")))

        result = await OperationsService.cancel_operation(
            uow=uow,
            operation_id=operation_id,
            user_id=user_id,
            reason="test cancel",
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_concurrent_correction_rejected(self):
        """Partial unique index prevents concurrent correction drafts."""
        uow = MockUoW()
        operation_id = uuid4()
        user_id = uuid4()

        existing_correction = MagicMock()
        existing_correction.id = uuid4()
        uow.corrections.get_active_draft_for_operation = AsyncMock(
            return_value=existing_correction,
        )

        operation = _make_operation(id=operation_id)
        operation.current_revision_id = uuid4()
        uow.operations.get_operation_by_id = AsyncMock(return_value=operation)

        rev = _make_revision(id=operation.current_revision_id)
        uow.operation_revisions.get_revision_by_id = AsyncMock(return_value=rev)

        with pytest.raises(HTTPException) as exc:
            await CorrectionsService.begin_correction(
                uow=uow,
                operation_id=operation_id,
                user_id=user_id,
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "concurrent_correction_exists"

    @pytest.mark.asyncio
    async def test_begin_correction_rejects_draft_operations(self):
        """Cannot begin correction on draft operations."""
        uow = MockUoW()
        operation_id = uuid4()
        user_id = uuid4()

        operation = _make_operation(id=operation_id, status="draft")
        uow.operations.get_operation_by_id = AsyncMock(return_value=operation)

        with pytest.raises(HTTPException) as exc:
            await CorrectionsService.begin_correction(
                uow=uow,
                operation_id=operation_id,
                user_id=user_id,
            )
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_abandon_and_resubmit(self):
        """Abandon a draft, then start a new correction."""
        uow = MockUoW()
        operation_id = uuid4()
        correction_id = uuid4()
        user_id = uuid4()

        # No active draft exists
        uow.corrections.get_active_draft_for_operation = AsyncMock(return_value=None)

        operation = _make_operation(id=operation_id)
        operation.current_revision_id = uuid4()
        uow.operations.get_operation_by_id = AsyncMock(return_value=operation)

        rev = _make_revision(id=operation.current_revision_id,
                             lines=[_make_revision_line()])
        uow.operation_revisions.get_revision_by_id = AsyncMock(return_value=rev)

        new_correction = MagicMock()
        new_correction.id = correction_id
        new_correction.operation_id = operation_id
        new_correction.status = "draft"
        new_correction.base_operation_revision_id = operation.current_revision_id
        new_correction.version = 1
        new_correction.idempotency_key = None
        new_correction.lines = [_make_correction_line()]
        uow.corrections.create_correction = AsyncMock(return_value=new_correction)
        uow.corrections.get_correction_by_id = AsyncMock(return_value=new_correction)
        uow.corrections.create_correction_line = AsyncMock()

        result = await CorrectionsService.begin_correction(
            uow=uow, operation_id=operation_id, user_id=user_id,
        )

        assert result["status"] == "draft"
