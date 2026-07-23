from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.services.corrections_service import (
    CORRECTION_KIND_ADDED,
    CORRECTION_KIND_ITEM_REPLACED,
    CORRECTION_KIND_METADATA_CHANGED,
    CORRECTION_KIND_QUANTITY_CHANGED,
    CORRECTION_KIND_REMOVED,
    CORRECTION_KIND_UNCHANGED,
    ComputedDiff,
    CorrectionsService,
)


def _make_bl(line_uuid, item_id=1, qty=100, batch=None, comment=None):
    bl = MagicMock()
    bl.line_uuid = line_uuid
    bl.line_number = 1
    bl.item_id = item_id
    bl.qty = Decimal(str(qty))
    bl.batch = batch
    bl.comment = comment
    return bl


def _make_cl(line_uuid=None, item_id=1, qty=100, line_number=1, batch=None, comment=None):
    cl = MagicMock()
    cl.line_uuid = line_uuid or uuid4()
    cl.line_number = line_number
    cl.item_id = item_id
    cl.qty = Decimal(str(qty))
    cl.batch = batch
    cl.comment = comment
    return cl


class MockUoW:
    def __init__(self):
        self.catalog = AsyncMock()
        self.balances = AsyncMock()
        self.inventory_subjects = AsyncMock()
        self.session = AsyncMock()


class TestComputeDiff:
    """Unit tests for _compute_correction_diff (server-side kind computation)."""

    @pytest.mark.asyncio
    async def test_compute_diff_unchanged(self):
        """All lines unchanged → no delta."""
        lu = uuid4()
        bl = _make_bl(lu)
        cl = _make_cl(lu)
        uow = MockUoW()
        baseline = MagicMock()
        baseline.lines = [bl]
        correction = MagicMock()
        correction.lines = [cl]

        diff = await CorrectionsService._compute_diff(uow, baseline, correction)

        assert len(diff.unchanged) == 1
        assert diff.unchanged[0]["line_uuid"] == lu
        assert diff.unchanged[0]["kind"] == CORRECTION_KIND_UNCHANGED
        assert len(diff.deltas) == 0

    @pytest.mark.asyncio
    async def test_compute_diff_quantity_change(self):
        """qty 100→120 → quantity_changed_same_item."""
        lu = uuid4()
        bl = _make_bl(lu, qty=100)
        cl = _make_cl(lu, qty=120)
        uow = MockUoW()
        baseline = MagicMock()
        baseline.lines = [bl]
        correction = MagicMock()
        correction.lines = [cl]

        diff = await CorrectionsService._compute_diff(uow, baseline, correction)

        assert len(diff.quantity_changed) == 1
        assert diff.quantity_changed[0]["line_uuid"] == lu
        assert diff.quantity_changed[0]["old_qty"] == Decimal("100")
        assert diff.quantity_changed[0]["new_qty"] == Decimal("120")
        assert diff.quantity_changed[0]["diff_qty"] == Decimal("20")
        assert diff.quantity_changed[0]["kind"] == CORRECTION_KIND_QUANTITY_CHANGED
        assert len(diff.deltas) == 1

    @pytest.mark.asyncio
    async def test_compute_diff_add_line(self):
        """New line_uuid → added."""
        existing_lu = uuid4()
        new_lu = uuid4()
        bl = _make_bl(existing_lu)
        cl1 = _make_cl(existing_lu)
        cl2 = _make_cl(new_lu, item_id=42, qty=10, batch="NEW")
        uow = MockUoW()
        baseline = MagicMock()
        baseline.lines = [bl]
        correction = MagicMock()
        correction.lines = [cl1, cl2]

        diff = await CorrectionsService._compute_diff(uow, baseline, correction)

        assert len(diff.added) == 1
        assert diff.added[0]["line_uuid"] == new_lu
        assert diff.added[0]["item_id"] == 42
        assert diff.added[0]["qty"] == Decimal("10")
        assert diff.added[0]["diff_qty"] == Decimal("10")
        assert diff.added[0]["kind"] == CORRECTION_KIND_ADDED

    @pytest.mark.asyncio
    async def test_compute_diff_remove_line(self):
        """Missing line_uuid → removed."""
        lu = uuid4()
        bl = _make_bl(lu, qty=100)
        uow = MockUoW()
        baseline = MagicMock()
        baseline.lines = [bl]
        correction = MagicMock()
        correction.lines = []

        diff = await CorrectionsService._compute_diff(uow, baseline, correction)

        assert len(diff.removed) == 1
        assert diff.removed[0]["line_uuid"] == lu
        assert diff.removed[0]["old_qty"] == Decimal("100")
        assert diff.removed[0]["diff_qty"] == Decimal("-100")
        assert diff.removed[0]["kind"] == CORRECTION_KIND_REMOVED

    @pytest.mark.asyncio
    async def test_compute_diff_replace_item(self):
        """item_id X→Y → item_replaced."""
        lu = uuid4()
        bl = _make_bl(lu, item_id=1, qty=50)
        cl = _make_cl(lu, item_id=2, qty=60)
        uow = MockUoW()
        baseline = MagicMock()
        baseline.lines = [bl]
        correction = MagicMock()
        correction.lines = [cl]

        diff = await CorrectionsService._compute_diff(uow, baseline, correction)

        assert len(diff.item_replaced) == 1
        assert diff.item_replaced[0]["line_uuid"] == lu
        assert diff.item_replaced[0]["old_item_id"] == 1
        assert diff.item_replaced[0]["new_item_id"] == 2
        assert diff.item_replaced[0]["diff_qty"] == Decimal("10")
        assert diff.item_replaced[0]["kind"] == CORRECTION_KIND_ITEM_REPLACED

    @pytest.mark.asyncio
    async def test_compute_diff_metadata_change(self):
        """batch change → metadata_changed."""
        lu = uuid4()
        bl = _make_bl(lu, batch="LOT-A", comment="old")
        cl = _make_cl(lu, batch="LOT-B", comment="new")
        uow = MockUoW()
        baseline = MagicMock()
        baseline.lines = [bl]
        correction = MagicMock()
        correction.lines = [cl]

        diff = await CorrectionsService._compute_diff(uow, baseline, correction)

        assert len(diff.metadata_changed) == 1
        assert diff.metadata_changed[0]["line_uuid"] == lu
        assert diff.metadata_changed[0]["kind"] == CORRECTION_KIND_METADATA_CHANGED

    @pytest.mark.asyncio
    async def test_compute_diff_baseline_none(self):
        """Baseline is None → all correction lines are added."""
        lu = uuid4()
        cl = _make_cl(lu, item_id=1, qty=50)
        uow = MockUoW()
        correction = MagicMock()
        correction.lines = [cl]

        diff = await CorrectionsService._compute_diff(uow, None, correction)

        assert len(diff.added) == 1
        assert len(diff.unchanged) == 0
        assert len(diff.removed) == 0

    @pytest.mark.asyncio
    async def test_compute_diff_combined(self):
        """Mixed changes in one diff."""
        lu_unchanged = uuid4()
        lu_changed = uuid4()
        lu_removed = uuid4()
        lu_added = uuid4()

        baseline = MagicMock()
        baseline.lines = [
            _make_bl(lu_unchanged),
            _make_bl(lu_changed, qty=10),
            _make_bl(lu_removed, qty=5),
        ]
        correction = MagicMock()
        correction.lines = [
            _make_cl(lu_unchanged),
            _make_cl(lu_changed, qty=20),
            _make_cl(lu_added, item_id=99, qty=15),
        ]
        uow = MockUoW()

        diff = await CorrectionsService._compute_diff(uow, baseline, correction)

        assert len(diff.unchanged) == 1
        assert diff.unchanged[0]["line_uuid"] == lu_unchanged
        assert len(diff.quantity_changed) == 1
        assert diff.quantity_changed[0]["line_uuid"] == lu_changed
        assert len(diff.added) == 1
        assert diff.added[0]["line_uuid"] == lu_added
        assert len(diff.removed) == 1
        assert diff.removed[0]["line_uuid"] == lu_removed
        assert len(diff.deltas) == 3  # only quantity_changed + added + removed


class TestCorrectionValidation:
    """Unit tests for correction validation logic."""

    def test_v1_scope_rejects_non_receive(self):
        uow = MockUoW()
        op = MagicMock()
        op.operation_type = "MOVE"
        op.acceptance_required = False

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            CorrectionsService._ensure_v1_scope(op)
        assert exc.value.status_code == 422
        detail = exc.value.detail
        assert detail["code"] == "correction_operation_type_not_supported"

    def test_v1_scope_rejects_acceptance_required(self):
        uow = MockUoW()
        op = MagicMock()
        op.operation_type = "RECEIVE"
        op.acceptance_required = True

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            CorrectionsService._ensure_v1_scope(op)
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "correction_acceptance_required_not_supported"

    def test_v1_scope_accepts_receive_no_acceptance(self):
        uow = MockUoW()
        op = MagicMock()
        op.operation_type = "RECEIVE"
        op.acceptance_required = False

        CorrectionsService._ensure_v1_scope(op)  # should not raise

    @pytest.mark.asyncio
    async def test_validate_sufficient_balance_ok(self):
        uow = MockUoW()
        subject = MagicMock()
        subject.id = 1
        uow.inventory_subjects.get_by_item_id = AsyncMock(return_value=subject)

        balance = MagicMock()
        balance.qty = Decimal("100")
        uow.balances.get_for_update = AsyncMock(return_value=balance)

        op = MagicMock()
        op.site_id = 1

        # Should not raise
        await CorrectionsService._validate_sufficient_balance(
            uow, op, item_id=1, required_qty=Decimal("50"), line_uuid=uuid4(),
        )

    @pytest.mark.asyncio
    async def test_validate_sufficient_balance_insufficient(self):
        uow = MockUoW()
        subject = MagicMock()
        subject.id = 1
        uow.inventory_subjects.get_by_item_id = AsyncMock(return_value=subject)

        balance = MagicMock()
        balance.qty = Decimal("30")
        uow.balances.get_for_update = AsyncMock(return_value=balance)

        op = MagicMock()
        op.site_id = 1

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await CorrectionsService._validate_sufficient_balance(
                uow, op, item_id=1, required_qty=Decimal("50"), line_uuid=uuid4(),
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "correction_insufficient_balance"
