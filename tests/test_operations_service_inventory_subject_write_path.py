from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.operations_service import OperationsService


def _operation_line(*, line_id: int, item_id: int, inventory_subject_id: int, qty: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=line_id,
        item_id=item_id,
        inventory_subject_id=inventory_subject_id,
        qty=qty,
        accepted_qty=0,
        lost_qty=0,
    )


@pytest.mark.asyncio
async def test_submit_receive_updates_balance_by_inventory_subject_id() -> None:
    operation = SimpleNamespace(
        id=uuid4(),
        status="draft",
        operation_type="RECEIVE",
        site_id=10,
        source_site_id=None,
        destination_site_id=None,
        acceptance_required=False,
        recipient_id=None,
        lines=[_operation_line(line_id=1, item_id=101, inventory_subject_id=5001, qty=3)],
    )
    operations = SimpleNamespace(
        get_operation_by_id=AsyncMock(side_effect=[operation]),
        submit_operation=AsyncMock(return_value=operation),
    )
    balances = SimpleNamespace(
        get_for_update=AsyncMock(),
        update_balance_quantity=AsyncMock(),
    )
    uow = SimpleNamespace(
        operations=operations,
        balances=balances,
        asset_registers=SimpleNamespace(upsert_pending=AsyncMock(), upsert_lost=AsyncMock(), upsert_issued=AsyncMock()),
    )

    await OperationsService.submit_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    balances.update_balance_quantity.assert_awaited_once_with(
        site_id=10,
        inventory_subject_id=5001,
        quantity_delta=Decimal("3"),
    )


@pytest.mark.asyncio
async def test_submit_issue_updates_issued_register_by_inventory_subject_id() -> None:
    operation = SimpleNamespace(
        id=uuid4(),
        status="draft",
        operation_type="ISSUE",
        site_id=10,
        source_site_id=None,
        destination_site_id=None,
        acceptance_required=False,
        recipient_id=77,
        lines=[_operation_line(line_id=1, item_id=101, inventory_subject_id=5001, qty=2)],
    )
    operations = SimpleNamespace(
        get_operation_by_id=AsyncMock(side_effect=[operation]),
        submit_operation=AsyncMock(return_value=operation),
    )
    balances = SimpleNamespace(
        get_for_update=AsyncMock(return_value=SimpleNamespace(qty=Decimal("10"))),
        update_balance_quantity=AsyncMock(),
    )
    asset_registers = SimpleNamespace(
        upsert_pending=AsyncMock(),
        upsert_lost=AsyncMock(),
        upsert_issued=AsyncMock(),
    )
    uow = SimpleNamespace(operations=operations, balances=balances, asset_registers=asset_registers)

    await OperationsService.submit_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    balances.get_for_update.assert_awaited_once_with(site_id=10, inventory_subject_id=5001)
    asset_registers.upsert_issued.assert_awaited_once_with(
        recipient_id=77,
        inventory_subject_id=5001,
        qty_delta=Decimal("2"),
    )

