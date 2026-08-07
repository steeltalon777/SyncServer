from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.operation_submit_errors import (
    InsufficientIssuedBalanceError,
    InsufficientStockError,
    OperationInWrongStateError,
    OperationNotFoundError,
    OperationSubmitError,
)
from app.services.operations_service import OperationsService


def _line(
    *,
    item_id: int,
    qty: int,
    id: int = 1,
    line_number: int = 1,
    accepted_qty: int = 0,
    lost_qty: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        item_id=item_id,
        inventory_subject_id=1000 + item_id,
        qty=qty,
        accepted_qty=accepted_qty,
        lost_qty=lost_qty,
        line_number=line_number,
    )


def _operation(
    *,
    operation_type: str,
    site_id: int = 1,
    source_site_id: int | None = None,
    destination_site_id: int | None = None,
    issue_object_id: int | None = None,
    acceptance_required: bool = False,
    status: str = "submitted",
    lines: list | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        status=status,
        operation_type=operation_type,
        site_id=site_id,
        source_site_id=source_site_id,
        destination_site_id=destination_site_id,
        acceptance_required=acceptance_required,
        issue_object_id=issue_object_id,
        lines=lines if lines is not None else [_line(item_id=10, qty=5)],
    )


def _balance_row(qty: str) -> SimpleNamespace:
    return SimpleNamespace(qty=Decimal(qty))


def _uow(
    operation,
    *,
    balance_qty: str = "10.000",
    issued_qty: str | None = None,
) -> SimpleNamespace:
    """Minimal UoW mock for cancel_operation unit tests.

    Lookup repos return display objects so deficit builders populate
    item/site/issue_object names (TZ §5.2); `requires_review=False` makes
    `_delete_temporary_items_of_operation` a no-op.
    """
    cancelled_operation = SimpleNamespace(
        id=operation.id,
        cancelled_at=datetime.now(UTC),
        origin="user",
    )
    subject = SimpleNamespace(
        id=1010,
        item_id=11,
        subject_type="catalog_item",
        temporary_item_id=None,
    )
    item = SimpleNamespace(
        id=11,
        name="Кабель ВВГ 3×2.5",
        unit_id=5,
        requires_review=False,
        deleted_at=None,
    )
    unit = SimpleNamespace(id=5, name="метр", symbol="м")
    return SimpleNamespace(
        balances=SimpleNamespace(
            get_for_update=AsyncMock(return_value=_balance_row(balance_qty)),
            update_balance_quantity=AsyncMock(),
        ),
        asset_registers=SimpleNamespace(
            upsert_pending=AsyncMock(),
            upsert_lost=AsyncMock(),
            upsert_issued=AsyncMock(),
            get_issued_balance=AsyncMock(
                return_value=_balance_row(issued_qty) if issued_qty is not None else None
            ),
        ),
        operations=SimpleNamespace(
            get_operation_by_id=AsyncMock(
                side_effect=[operation, operation],  # cancel + _delete_temporary_items
            ),
            cancel_operation=AsyncMock(return_value=cancelled_operation),
        ),
        inventory_subjects=SimpleNamespace(get_by_id=AsyncMock(return_value=subject)),
        catalog=SimpleNamespace(
            get_item_by_id=AsyncMock(return_value=item),
            get_unit_by_id=AsyncMock(return_value=unit),
        ),
        sites=SimpleNamespace(
            get_by_id=AsyncMock(side_effect=lambda site_id: SimpleNamespace(id=site_id, name=f"Склад {site_id}"))
        ),
        issue_objects=SimpleNamespace(
            get_by_id=AsyncMock(return_value=SimpleNamespace(id=77, display_name="Иванов Иван"))
        ),
        session=SimpleNamespace(flush=AsyncMock()),
        audit_events=SimpleNamespace(
            insert=AsyncMock(return_value=SimpleNamespace(id=1)),
            insert_effect=AsyncMock(),
        ),
    )


@pytest.mark.asyncio
async def test_cancel_receive_is_blocked_if_rollback_would_make_balance_negative() -> None:
    operation = _operation(operation_type="RECEIVE", site_id=1)
    uow = _uow(operation, balance_qty="2.000")

    with pytest.raises(InsufficientStockError) as exc:
        await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    assert not isinstance(exc.value, HTTPException)
    assert exc.value.http_status == 409
    assert exc.value.problem_class == "operation-cancel-rejected"
    assert len(exc.value.deficits) == 1
    deficit = exc.value.deficits[0]
    assert deficit.stock_site_id == 1
    assert deficit.required_qty == Decimal("5")
    assert deficit.available_qty == Decimal("2")
    assert deficit.operation_line_ids == [1]
    envelope = exc.value.to_envelope()
    assert envelope.code == "operation_cancel_rejected"
    assert envelope.type == "urn:warehouse:problem:operation-cancel-rejected"
    assert envelope.errors[0].code == "insufficient_stock"
    uow.balances.update_balance_quantity.assert_not_awaited()
    uow.operations.cancel_operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_move_is_blocked_if_destination_cannot_return_stock() -> None:
    operation = _operation(operation_type="MOVE", source_site_id=1, destination_site_id=2)
    uow = _uow(operation, balance_qty="1.000")

    with pytest.raises(InsufficientStockError) as exc:
        await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    assert not isinstance(exc.value, HTTPException)
    assert exc.value.http_status == 409
    assert exc.value.problem_class == "operation-cancel-rejected"
    deficit = exc.value.deficits[0]
    assert deficit.stock_site_id == 2
    assert deficit.required_qty == Decimal("5")
    assert deficit.available_qty == Decimal("1")
    assert exc.value.to_envelope().errors[0].code == "insufficient_stock"
    uow.balances.update_balance_quantity.assert_not_awaited()
    uow.operations.cancel_operation.assert_not_awaited()


# ---------------------------------------------------------------------------
# Happy path: every operation type cancels with a sufficient balance (TZ §10.2 #14)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_receive_happy_path_decrements_warehouse() -> None:
    operation = _operation(operation_type="RECEIVE", site_id=1)
    uow = _uow(operation)

    await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    uow.balances.update_balance_quantity.assert_awaited_once_with(
        site_id=1, inventory_subject_id=1010, quantity_delta=Decimal("-5"),
    )
    uow.operations.cancel_operation.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_expense_happy_path_restores_warehouse() -> None:
    operation = _operation(operation_type="EXPENSE", site_id=1)
    uow = _uow(operation)

    await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    uow.balances.update_balance_quantity.assert_awaited_once_with(
        site_id=1, inventory_subject_id=1010, quantity_delta=Decimal("5"),
    )
    uow.asset_registers.upsert_issued.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_warehouse_write_off_happy_path_restores_warehouse() -> None:
    operation = _operation(operation_type="WRITE_OFF", issue_object_id=None)
    uow = _uow(operation)

    await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    uow.balances.update_balance_quantity.assert_awaited_once_with(
        site_id=1, inventory_subject_id=1010, quantity_delta=Decimal("5"),
    )


@pytest.mark.asyncio
async def test_cancel_object_write_off_happy_path_restores_issued_only() -> None:
    operation = _operation(operation_type="WRITE_OFF", issue_object_id=77)
    uow = _uow(operation)

    await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    uow.asset_registers.upsert_issued.assert_awaited_once_with(
        issue_object_id=77, inventory_subject_id=1010, qty_delta=Decimal("5"),
    )
    uow.balances.update_balance_quantity.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_adjustment_happy_path_inverts_delta() -> None:
    operation = _operation(operation_type="ADJUSTMENT", site_id=1)
    uow = _uow(operation)

    await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    uow.balances.update_balance_quantity.assert_awaited_once_with(
        site_id=1, inventory_subject_id=1010, quantity_delta=Decimal("-5"),
    )


@pytest.mark.asyncio
async def test_cancel_move_happy_path_returns_to_source_and_drains_destination() -> None:
    operation = _operation(operation_type="MOVE", source_site_id=1, destination_site_id=2)
    uow = _uow(operation)

    await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    assert uow.balances.update_balance_quantity.await_count == 2
    uow.balances.update_balance_quantity.assert_any_await(
        site_id=1, inventory_subject_id=1010, quantity_delta=Decimal("5"),
    )
    uow.balances.update_balance_quantity.assert_any_await(
        site_id=2, inventory_subject_id=1010, quantity_delta=Decimal("-5"),
    )


@pytest.mark.asyncio
async def test_cancel_move_with_acceptance_uses_accepted_qty() -> None:
    operation = _operation(
        operation_type="MOVE",
        source_site_id=1,
        destination_site_id=2,
        acceptance_required=True,
        lines=[_line(item_id=10, qty=8, accepted_qty=5)],
    )
    uow = _uow(operation)

    await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    assert uow.balances.update_balance_quantity.await_count == 2
    uow.balances.update_balance_quantity.assert_any_await(
        site_id=1, inventory_subject_id=1010, quantity_delta=Decimal("8"),
    )
    uow.balances.update_balance_quantity.assert_any_await(
        site_id=2, inventory_subject_id=1010, quantity_delta=Decimal("-5"),
    )


@pytest.mark.asyncio
async def test_cancel_issue_happy_path_restores_warehouse_and_drains_issued() -> None:
    operation = _operation(operation_type="ISSUE", site_id=1, issue_object_id=77)
    uow = _uow(operation, issued_qty="10.000")

    await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    uow.balances.update_balance_quantity.assert_awaited_once_with(
        site_id=1, inventory_subject_id=1010, quantity_delta=Decimal("5"),
    )
    uow.asset_registers.upsert_issued.assert_awaited_once_with(
        issue_object_id=77, inventory_subject_id=1010, qty_delta=Decimal("-5"),
    )


@pytest.mark.asyncio
async def test_cancel_issue_return_happy_path_restores_issued_and_drains_warehouse() -> None:
    operation = _operation(operation_type="ISSUE_RETURN", site_id=1, issue_object_id=77)
    uow = _uow(operation, issued_qty="10.000")

    await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    uow.balances.update_balance_quantity.assert_awaited_once_with(
        site_id=1, inventory_subject_id=1010, quantity_delta=Decimal("-5"),
    )
    uow.asset_registers.upsert_issued.assert_awaited_once_with(
        issue_object_id=77, inventory_subject_id=1010, qty_delta=Decimal("5"),
    )


# ---------------------------------------------------------------------------
# Envelope on rollback deficit: warehouse and issued (TZ §10.2 #15)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_receive_deficit_produces_insufficient_stock_envelope() -> None:
    operation = _operation(operation_type="RECEIVE", site_id=1)
    uow = _uow(operation, balance_qty="0.000")

    with pytest.raises(InsufficientStockError) as exc:
        await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    deficit = exc.value.deficits[0]
    assert deficit.required_qty == Decimal("5")
    assert deficit.available_qty == Decimal("0")
    assert deficit.operation_line_ids == [1]
    envelope = exc.value.to_envelope()
    assert envelope.status == 409
    assert envelope.code == "operation_cancel_rejected"
    assert envelope.errors[0].code == "insufficient_stock"
    assert isinstance(envelope.detail, str)
    assert "Недостаточно товара" in envelope.detail
    uow.operations.cancel_operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_issue_deficit_produces_insufficient_issued_balance_envelope() -> None:
    operation = _operation(operation_type="ISSUE", site_id=1, issue_object_id=77)
    uow = _uow(operation, issued_qty="2.000")

    with pytest.raises(InsufficientIssuedBalanceError) as exc:
        await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    deficit = exc.value.deficits[0]
    assert deficit.issue_object_id == 77
    assert deficit.required_qty == Decimal("5")
    assert deficit.available_qty == Decimal("2")
    envelope = exc.value.to_envelope()
    assert envelope.status == 409
    assert envelope.code == "operation_cancel_rejected"
    assert envelope.errors[0].code == "insufficient_issued_balance"
    assert envelope.errors[0].issue_object.id == 77
    uow.operations.cancel_operation.assert_not_awaited()
    uow.asset_registers.upsert_issued.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_issue_return_deficit_blocks_on_warehouse() -> None:
    operation = _operation(operation_type="ISSUE_RETURN", site_id=1, issue_object_id=77)
    uow = _uow(operation, balance_qty="0.000", issued_qty="10.000")

    with pytest.raises(InsufficientStockError) as exc:
        await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    assert exc.value.deficits[0].stock_site_id == 1
    uow.operations.cancel_operation.assert_not_awaited()


# ---------------------------------------------------------------------------
# Workflow domain errors raised by cancel_operation (TZ §10.2 #17)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_already_cancelled_raises_operation_in_wrong_state() -> None:
    operation = _operation(operation_type="RECEIVE", status="cancelled")
    uow = _uow(operation)

    with pytest.raises(OperationInWrongStateError) as exc:
        await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    assert not isinstance(exc.value, HTTPException)
    assert exc.value.http_status == 409
    assert exc.value.current_state == "cancelled"
    assert exc.value.allowed_states == ["draft", "submitted"]
    assert exc.value.problem_class == "operation-cancel-rejected"
    envelope = exc.value.to_envelope()
    assert envelope.code == "operation_cancel_rejected"
    assert envelope.errors[0].code == "operation_in_wrong_state"
    assert envelope.errors[0].current_state == "cancelled"
    uow.balances.get_for_update.assert_not_awaited()
    uow.operations.cancel_operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_missing_operation_raises_operation_not_found() -> None:
    operation_id = uuid4()
    uow = _uow(_operation(operation_type="RECEIVE"))
    uow.operations.get_operation_by_id = AsyncMock(return_value=None)

    with pytest.raises(OperationNotFoundError) as exc:
        await OperationsService.cancel_operation(uow=uow, operation_id=operation_id, user_id=uuid4())

    assert not isinstance(exc.value, HTTPException)
    assert exc.value.http_status == 404
    assert exc.value.operation_id is None  # require_exists(None) has no id to pass
    envelope = exc.value.to_envelope()
    assert envelope.code == "operation_not_found"
    assert envelope.type == "urn:warehouse:problem:operation-not-found"
    assert envelope.errors[0].code == "operation_not_found"
    uow.balances.get_for_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_rollback_failures_leave_no_audit_event() -> None:
    """A blocked cancel must not write an audit event or mutate balances."""
    operation = _operation(operation_type="RECEIVE", site_id=1)
    uow = _uow(operation, balance_qty="0.000")

    with pytest.raises(InsufficientStockError):
        await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    uow.balances.update_balance_quantity.assert_not_awaited()
    uow.operations.cancel_operation.assert_not_awaited()
    uow.audit_events.insert.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_errors_are_operation_submit_error_not_http_exception() -> None:
    """All cancel-flow failures raise OperationSubmitError subclasses (envelope), never HTTPException."""
    for exc_type, build_uow in [
        (
            InsufficientStockError,
            lambda op: _uow(op, balance_qty="0.000"),
        ),
        (
            OperationInWrongStateError,
            lambda op: _uow(_operation(operation_type="RECEIVE", status="cancelled")),
        ),
        (
            OperationNotFoundError,
            lambda op: _uow(op),
        ),
    ]:
        operation = _operation(operation_type="RECEIVE", site_id=1)
        uow = build_uow(operation)
        if exc_type is OperationNotFoundError:
            uow.operations.get_operation_by_id = AsyncMock(return_value=None)
        with pytest.raises(exc_type) as exc:
            await OperationsService.cancel_operation(uow=uow, operation_id=operation.id, user_id=uuid4())
        assert isinstance(exc.value, OperationSubmitError)
        assert not isinstance(exc.value, HTTPException)
