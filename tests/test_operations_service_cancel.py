from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.operations_service import OperationsService


def _line(*, item_id: int, qty: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        item_id=item_id,
        inventory_subject_id=1000 + item_id,
        qty=qty,
        accepted_qty=0,
        lost_qty=0,
    )


def _operation(
    *,
    operation_type: str,
    site_id: int = 1,
    source_site_id: int | None = None,
    destination_site_id: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        status="submitted",
        operation_type=operation_type,
        site_id=site_id,
        source_site_id=source_site_id,
        destination_site_id=destination_site_id,
        acceptance_required=False,
        recipient_id=None,
        lines=[_line(item_id=10, qty=5)],
    )


@pytest.mark.asyncio
async def test_cancel_receive_is_blocked_if_rollback_would_make_balance_negative() -> None:
    operation = _operation(operation_type="RECEIVE", site_id=1)
    balances = SimpleNamespace(
        get_for_update=AsyncMock(return_value=SimpleNamespace(qty=Decimal("2"))),
        update_balance_quantity=AsyncMock(),
    )
    operations = SimpleNamespace(
        get_operation_by_id=AsyncMock(return_value=operation),
        cancel_operation=AsyncMock(),
    )
    uow = SimpleNamespace(balances=balances, operations=operations)

    with pytest.raises(HTTPException) as exc:
        await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    assert exc.value.status_code == 409
    balances.update_balance_quantity.assert_not_awaited()
    operations.cancel_operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_move_is_blocked_if_destination_cannot_return_stock() -> None:
    operation = _operation(operation_type="MOVE", source_site_id=1, destination_site_id=2)
    balances = SimpleNamespace(
        get_for_update=AsyncMock(side_effect=[SimpleNamespace(qty=Decimal("1"))]),
        update_balance_quantity=AsyncMock(),
    )
    operations = SimpleNamespace(
        get_operation_by_id=AsyncMock(return_value=operation),
        cancel_operation=AsyncMock(),
    )
    uow = SimpleNamespace(balances=balances, operations=operations)

    with pytest.raises(HTTPException) as exc:
        await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    assert exc.value.status_code == 409
    balances.update_balance_quantity.assert_not_awaited()
    operations.cancel_operation.assert_not_awaited()
