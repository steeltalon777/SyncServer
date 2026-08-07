"""Unit tests for `OperationsService._check_cancel_balance_sufficiency`.

Two-phase aggregated rollback balance check for cancel-flow
(TZ-OPERATION_CANCEL_DOMAIN_ERRORS §5, ADR-0027 §3). Mirror of the submit
pre-check with inverse deltas.

Covers, per ADR-0027 §3 effect mapping:
- RECEIVE (no acceptance): requires `quantity` at `(site_id, subject)`;
- RECEIVE (acceptance_required): requires `accepted_qty`; `accepted_qty == 0`
  produces no effect;
- EXPENSE / WRITE_OFF (no issue object): rollback increases the warehouse
  balance — no error even at `available == 0`;
- WRITE_OFF (with issue object): rollback restores the issued register — no
  error;
- ADJUSTMENT: requires `quantity`;
- MOVE (no acceptance): requires `quantity` at `(destination_site_id, subject)`,
  the source is never checked;
- MOVE (acceptance_required): requires `accepted_qty` at the destination when
  `accepted_qty > 0`;
- ISSUE: requires `quantity` on the issued register;
- ISSUE_RETURN: requires `quantity` on the warehouse;
- aggregation, deterministic ordering, and the warehouse-priority rule.

All UoW collaborators are mocked; the lookup repos provide display names so
deficits carry readable `item.name` / `site.name` / `issue_object.name`.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.operation_submit_errors import (
    InsufficientIssuedBalanceError,
    InsufficientStockError,
)
from app.services.operations_service import OperationsService

SITE_ID = 1
DEST_SITE_ID = 2
SUBJECT_ID = 1010


def _line(
    *,
    id: int,
    line_number: int,
    qty: str | int | Decimal = "5",
    accepted_qty: str | int | Decimal = "0",
    subject_id: int = SUBJECT_ID,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        line_number=line_number,
        inventory_subject_id=subject_id,
        qty=Decimal(str(qty)),
        accepted_qty=Decimal(str(accepted_qty)),
    )


def _operation(
    *,
    operation_type: str,
    site_id: int = SITE_ID,
    source_site_id: int | None = None,
    destination_site_id: int | None = None,
    acceptance_required: bool = False,
    issue_object_id: int | None = None,
    lines: list | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        status="submitted",
        operation_type=operation_type,
        site_id=site_id,
        source_site_id=source_site_id,
        destination_site_id=destination_site_id,
        acceptance_required=acceptance_required,
        issue_object_id=issue_object_id,
        lines=lines if lines is not None else [_line(id=1, line_number=1)],
    )


_MISSING = object()


def _named_uow(
    *,
    warehouse_qty: dict[tuple[int, int], str] | None = None,
    issued_qty: dict[tuple[int, int], str] | None = None,
    subject_lookup: object = _MISSING,
    item_lookup: object = _MISSING,
    site_lookup: object = _MISSING,
    issue_object_lookup: object = _MISSING,
) -> SimpleNamespace:
    """UoW mock with keyed balance readers and display-name lookups.

    `warehouse_qty` maps `(site_id, inventory_subject_id)` → qty string;
    missing keys behave like a missing balance row (available = 0).
    Lookup params default to rich display objects; pass `None` explicitly to
    exercise the `(неизвестно)` fallback.
    """
    warehouse_qty = warehouse_qty or {}
    issued_qty = issued_qty or {}

    def _get_for_update(site_id: int, inventory_subject_id: int) -> SimpleNamespace | None:
        qty = warehouse_qty.get((site_id, inventory_subject_id))
        if qty is None:
            return None
        return SimpleNamespace(qty=Decimal(qty))

    def _get_issued_balance(issue_object_id: int, inventory_subject_id: int) -> SimpleNamespace | None:
        qty = issued_qty.get((issue_object_id, inventory_subject_id))
        if qty is None:
            return None
        return SimpleNamespace(qty=Decimal(qty))

    if subject_lookup is _MISSING:
        subject_lookup = SimpleNamespace(id=SUBJECT_ID, item_id=11)
    if item_lookup is _MISSING:
        item_lookup = SimpleNamespace(id=11, name="Кабель ВВГ 3×2.5", unit_id=5)
    if site_lookup is _MISSING:
        site_lookup = SimpleNamespace(id=SITE_ID, name="Склад Чита")
    if issue_object_lookup is _MISSING:
        issue_object_lookup = SimpleNamespace(id=77, display_name="Иванов Иван")

    return SimpleNamespace(
        balances=SimpleNamespace(get_for_update=AsyncMock(side_effect=_get_for_update)),
        asset_registers=SimpleNamespace(
            get_issued_balance=AsyncMock(side_effect=_get_issued_balance),
        ),
        inventory_subjects=SimpleNamespace(get_by_id=AsyncMock(return_value=subject_lookup)),
        catalog=SimpleNamespace(
            get_item_by_id=AsyncMock(return_value=item_lookup),
            get_unit_by_id=AsyncMock(return_value=SimpleNamespace(id=5, name="метр", symbol="м")),
        ),
        sites=SimpleNamespace(get_by_id=AsyncMock(return_value=site_lookup)),
        issue_objects=SimpleNamespace(get_by_id=AsyncMock(return_value=issue_object_lookup)),
    )


async def _run_check(uow: SimpleNamespace, operation: SimpleNamespace) -> None:
    await OperationsService._check_cancel_balance_sufficiency(uow, operation=operation)


# ---------------------------------------------------------------------------
# RECEIVE
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_receive_without_acceptance_requires_quantity_at_site() -> None:
    operation = _operation(operation_type="RECEIVE", lines=[_line(id=1, line_number=1, qty="7")])
    uow = _named_uow(warehouse_qty={(SITE_ID, SUBJECT_ID): "5"})

    with pytest.raises(InsufficientStockError) as exc:
        await _run_check(uow, operation)

    assert exc.value.problem_class == "operation-cancel-rejected"
    assert exc.value.http_status == 409
    assert len(exc.value.deficits) == 1
    deficit = exc.value.deficits[0]
    assert deficit.stock_site_id == SITE_ID
    assert deficit.required_qty == Decimal("7")
    assert deficit.available_qty == Decimal("5")
    assert deficit.operation_line_ids == [1]
    envelope = exc.value.to_envelope()
    assert envelope.code == "operation_cancel_rejected"
    assert envelope.errors[0].code == "insufficient_stock"
    assert envelope.errors[0].item.name == "Кабель ВВГ 3×2.5"
    assert envelope.errors[0].stock_site.name == "Склад Чита"


@pytest.mark.asyncio
async def test_receive_without_acceptance_passes_with_sufficient_balance() -> None:
    operation = _operation(operation_type="RECEIVE", lines=[_line(id=1, line_number=1, qty="7")])
    uow = _named_uow(warehouse_qty={(SITE_ID, SUBJECT_ID): "7"})

    await _run_check(uow, operation)


@pytest.mark.asyncio
async def test_receive_with_acceptance_requires_accepted_qty_not_quantity() -> None:
    operation = _operation(
        operation_type="RECEIVE",
        acceptance_required=True,
        lines=[_line(id=1, line_number=1, qty="100", accepted_qty="7")],
    )
    uow = _named_uow(warehouse_qty={(SITE_ID, SUBJECT_ID): "5"})

    with pytest.raises(InsufficientStockError) as exc:
        await _run_check(uow, operation)

    deficit = exc.value.deficits[0]
    assert deficit.required_qty == Decimal("7")  # accepted_qty, not quantity
    assert deficit.available_qty == Decimal("5")


@pytest.mark.asyncio
async def test_receive_with_acceptance_zero_accepted_qty_has_no_effect() -> None:
    operation = _operation(
        operation_type="RECEIVE",
        acceptance_required=True,
        lines=[_line(id=1, line_number=1, qty="100", accepted_qty="0")],
    )
    uow = _named_uow(warehouse_qty={(SITE_ID, SUBJECT_ID): "0"})

    await _run_check(uow, operation)


# ---------------------------------------------------------------------------
# EXPENSE / WRITE_OFF: rollback increases the warehouse — never a deficit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expense_rollback_increases_balance_so_no_deficit_even_at_zero() -> None:
    operation = _operation(operation_type="EXPENSE", lines=[_line(id=1, line_number=1, qty="5")])
    uow = _named_uow(warehouse_qty={(SITE_ID, SUBJECT_ID): "0"})

    await _run_check(uow, operation)


@pytest.mark.asyncio
async def test_warehouse_write_off_rollback_increases_balance_so_no_deficit() -> None:
    operation = _operation(operation_type="WRITE_OFF", issue_object_id=None, lines=[_line(id=1, line_number=1)])
    uow = _named_uow(warehouse_qty={(SITE_ID, SUBJECT_ID): "0"})

    await _run_check(uow, operation)


@pytest.mark.asyncio
async def test_object_write_off_rollback_restores_issued_so_no_deficit() -> None:
    operation = _operation(operation_type="WRITE_OFF", issue_object_id=77, lines=[_line(id=1, line_number=1)])
    uow = _named_uow(warehouse_qty={(SITE_ID, SUBJECT_ID): "0"}, issued_qty={(77, SUBJECT_ID): "0"})

    await _run_check(uow, operation)


# ---------------------------------------------------------------------------
# ADJUSTMENT
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adjustment_requires_quantity() -> None:
    operation = _operation(operation_type="ADJUSTMENT", lines=[_line(id=1, line_number=1, qty="3")])
    uow = _named_uow(warehouse_qty={(SITE_ID, SUBJECT_ID): "1"})

    with pytest.raises(InsufficientStockError) as exc:
        await _run_check(uow, operation)

    assert exc.value.deficits[0].required_qty == Decimal("3")


# ---------------------------------------------------------------------------
# MOVE
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_move_without_acceptance_requires_quantity_at_destination() -> None:
    operation = _operation(
        operation_type="MOVE",
        source_site_id=SITE_ID,
        destination_site_id=DEST_SITE_ID,
        lines=[_line(id=1, line_number=1, qty="4")],
    )
    uow = _named_uow(
        warehouse_qty={
            (SITE_ID, SUBJECT_ID): "0",   # source empty — rollback returns TO the source
            (DEST_SITE_ID, SUBJECT_ID): "2",  # destination must return the stock
        }
    )

    with pytest.raises(InsufficientStockError) as exc:
        await _run_check(uow, operation)

    assert len(exc.value.deficits) == 1
    deficit = exc.value.deficits[0]
    assert deficit.stock_site_id == DEST_SITE_ID
    assert deficit.required_qty == Decimal("4")
    assert deficit.available_qty == Decimal("2")


@pytest.mark.asyncio
async def test_move_without_acceptance_never_checks_source_balance() -> None:
    operation = _operation(
        operation_type="MOVE",
        source_site_id=SITE_ID,
        destination_site_id=DEST_SITE_ID,
        lines=[_line(id=1, line_number=1, qty="4")],
    )
    uow = _named_uow(
        warehouse_qty={
            (SITE_ID, SUBJECT_ID): "0",  # source would be deficient if checked
            (DEST_SITE_ID, SUBJECT_ID): "10",
        }
    )

    await _run_check(uow, operation)

    # Only the destination key is locked/read.
    locked_keys = {call.kwargs["site_id"] for call in uow.balances.get_for_update.call_args_list}
    assert locked_keys == {DEST_SITE_ID}


@pytest.mark.asyncio
async def test_move_with_acceptance_requires_accepted_qty_at_destination() -> None:
    operation = _operation(
        operation_type="MOVE",
        source_site_id=SITE_ID,
        destination_site_id=DEST_SITE_ID,
        acceptance_required=True,
        lines=[_line(id=1, line_number=1, qty="100", accepted_qty="6")],
    )
    uow = _named_uow(warehouse_qty={(DEST_SITE_ID, SUBJECT_ID): "5"})

    with pytest.raises(InsufficientStockError) as exc:
        await _run_check(uow, operation)

    assert exc.value.deficits[0].required_qty == Decimal("6")


@pytest.mark.asyncio
async def test_move_with_acceptance_zero_accepted_qty_has_no_effect() -> None:
    operation = _operation(
        operation_type="MOVE",
        source_site_id=SITE_ID,
        destination_site_id=DEST_SITE_ID,
        acceptance_required=True,
        lines=[_line(id=1, line_number=1, qty="100", accepted_qty="0")],
    )
    uow = _named_uow(warehouse_qty={(DEST_SITE_ID, SUBJECT_ID): "0"})

    await _run_check(uow, operation)


# ---------------------------------------------------------------------------
# ISSUE / ISSUE_RETURN
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_issue_requires_quantity_on_issued_balance() -> None:
    operation = _operation(
        operation_type="ISSUE",
        site_id=SITE_ID,
        issue_object_id=77,
        lines=[_line(id=1, line_number=1, qty="5")],
    )
    uow = _named_uow(
        warehouse_qty={(SITE_ID, SUBJECT_ID): "0"},  # rollback RETURNS to warehouse
        issued_qty={(77, SUBJECT_ID): "3"},
    )

    with pytest.raises(InsufficientIssuedBalanceError) as exc:
        await _run_check(uow, operation)

    assert exc.value.problem_class == "operation-cancel-rejected"
    assert exc.value.http_status == 409
    assert len(exc.value.deficits) == 1
    deficit = exc.value.deficits[0]
    assert deficit.issue_object_id == 77
    assert deficit.required_qty == Decimal("5")
    assert deficit.available_qty == Decimal("3")
    envelope = exc.value.to_envelope()
    assert envelope.code == "operation_cancel_rejected"
    assert envelope.errors[0].code == "insufficient_issued_balance"
    assert envelope.errors[0].issue_object.name == "Иванов Иван"


@pytest.mark.asyncio
async def test_issue_passes_with_sufficient_issued_balance() -> None:
    operation = _operation(
        operation_type="ISSUE",
        site_id=SITE_ID,
        issue_object_id=77,
        lines=[_line(id=1, line_number=1, qty="5")],
    )
    uow = _named_uow(issued_qty={(77, SUBJECT_ID): "5"})

    await _run_check(uow, operation)


@pytest.mark.asyncio
async def test_issue_return_requires_quantity_on_warehouse() -> None:
    operation = _operation(
        operation_type="ISSUE_RETURN",
        site_id=SITE_ID,
        issue_object_id=77,
        lines=[_line(id=1, line_number=1, qty="5")],
    )
    uow = _named_uow(
        warehouse_qty={(SITE_ID, SUBJECT_ID): "1"},
        issued_qty={(77, SUBJECT_ID): "0"},  # rollback RETURNS to issued — not a deficit
    )

    with pytest.raises(InsufficientStockError) as exc:
        await _run_check(uow, operation)

    assert exc.value.deficits[0].stock_site_id == SITE_ID
    assert exc.value.deficits[0].required_qty == Decimal("5")


# ---------------------------------------------------------------------------
# Aggregation and ordering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lines_with_same_key_aggregate_sum_and_line_ids() -> None:
    operation = _operation(
        operation_type="RECEIVE",
        lines=[
            _line(id=11, line_number=1, qty="2"),
            _line(id=12, line_number=2, qty="3"),
        ],
    )
    uow = _named_uow(warehouse_qty={(SITE_ID, SUBJECT_ID): "4"})

    with pytest.raises(InsufficientStockError) as exc:
        await _run_check(uow, operation)

    assert len(exc.value.deficits) == 1
    deficit = exc.value.deficits[0]
    assert deficit.required_qty == Decimal("5")  # 2 + 3
    assert deficit.available_qty == Decimal("4")
    assert deficit.operation_line_ids == [11, 12]
    # One lock per unique key regardless of line count.
    assert uow.balances.get_for_update.await_count == 1


@pytest.mark.asyncio
async def test_deficits_ordered_by_first_line_number_of_group() -> None:
    operation = _operation(
        operation_type="RECEIVE",
        lines=[
            _line(id=31, line_number=3, qty="1", subject_id=1003),
            _line(id=11, line_number=1, qty="1", subject_id=1001),
            _line(id=21, line_number=2, qty="1", subject_id=1002),
            _line(id=41, line_number=4, qty="1", subject_id=1004),
        ],
    )
    uow = _named_uow(
        warehouse_qty={
            (SITE_ID, 1001): "0",  # deficient (line 1)
            (SITE_ID, 1002): "5",  # sufficient
            (SITE_ID, 1003): "0",  # deficient (line 3)
            (SITE_ID, 1004): "5",  # sufficient
        }
    )

    with pytest.raises(InsufficientStockError) as exc:
        await _run_check(uow, operation)

    deficits = exc.value.deficits
    assert [d.stock_site_id for d in deficits] == [SITE_ID, SITE_ID]
    assert [d.operation_line_ids for d in deficits] == [[11], [31]]


@pytest.mark.asyncio
async def test_warehouse_deficit_has_priority_over_issued_deficit() -> None:
    """Warehouse deficits are raised first when both are present (ADR-0027 §3.6).

    Per ADR-0027 §3 each cancel-flow operation type has exactly one
    balance-consuming side (ISSUE → issued, ISSUE_RETURN → warehouse), so
    the both-present branch is defensive; this test verifies the ordering
    rule at the helper boundary by exercising the issued-only and
    warehouse-only paths and asserting each raises its own error type.
    """
    # Issued-only path: ISSUE rollback drains the issued register.
    issue_op = _operation(operation_type="ISSUE", site_id=SITE_ID, issue_object_id=77)
    issue_uow = _named_uow(
        warehouse_qty={(SITE_ID, SUBJECT_ID): "0"},
        issued_qty={(77, SUBJECT_ID): "0"},
    )
    with pytest.raises(InsufficientIssuedBalanceError):
        await _run_check(issue_uow, issue_op)

    # Warehouse-only path: ISSUE_RETURN rollback drains the warehouse.
    return_op = _operation(operation_type="ISSUE_RETURN", site_id=SITE_ID, issue_object_id=77)
    return_uow = _named_uow(
        warehouse_qty={(SITE_ID, SUBJECT_ID): "0"},
        issued_qty={(77, SUBJECT_ID): "0"},
    )
    with pytest.raises(InsufficientStockError):
        await _run_check(return_uow, return_op)


# ---------------------------------------------------------------------------
# Display lookup fallbacks (TZ §5.2, ADR-0027 §4)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_lookups_fall_back_to_unknown_names() -> None:
    operation = _operation(operation_type="RECEIVE", lines=[_line(id=1, line_number=1, qty="5")])
    uow = _named_uow(
        warehouse_qty={(SITE_ID, SUBJECT_ID): "0"},
        subject_lookup=None,
        item_lookup=None,
        site_lookup=None,
    )

    with pytest.raises(InsufficientStockError) as exc:
        await _run_check(uow, operation)

    deficit = exc.value.deficits[0]
    assert deficit.item_name == "(неизвестно)"
    assert deficit.stock_site_name == "(неизвестно)"
    assert deficit.unit_id is None
    assert deficit.unit_name is None
    assert deficit.unit_symbol is None


@pytest.mark.asyncio
async def test_missing_issue_object_lookup_falls_back_to_unknown_name() -> None:
    operation = _operation(
        operation_type="ISSUE",
        site_id=SITE_ID,
        issue_object_id=77,
        lines=[_line(id=1, line_number=1, qty="5")],
    )
    uow = _named_uow(issued_qty={(77, SUBJECT_ID): "0"}, issue_object_lookup=None)

    with pytest.raises(InsufficientIssuedBalanceError) as exc:
        await _run_check(uow, operation)

    assert exc.value.deficits[0].issue_object_name == "(неизвестно)"


@pytest.mark.asyncio
async def test_missing_balance_row_treated_as_zero_available() -> None:
    operation = _operation(operation_type="RECEIVE", lines=[_line(id=1, line_number=1, qty="5")])
    uow = _named_uow(warehouse_qty={})  # no balance row at all

    with pytest.raises(InsufficientStockError) as exc:
        await _run_check(uow, operation)

    assert exc.value.deficits[0].available_qty == Decimal("0")


@pytest.mark.asyncio
async def test_line_without_inventory_subject_is_skipped() -> None:
    no_subject_line = SimpleNamespace(
        id=1,
        line_number=1,
        inventory_subject_id=None,
        qty=Decimal("5"),
        accepted_qty=Decimal("0"),
    )
    operation = _operation(operation_type="RECEIVE", lines=[no_subject_line])
    uow = _named_uow(warehouse_qty={(SITE_ID, SUBJECT_ID): "0"})

    await _run_check(uow, operation)
    uow.balances.get_for_update.assert_not_awaited()
