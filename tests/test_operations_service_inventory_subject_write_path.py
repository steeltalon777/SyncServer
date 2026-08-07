from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.audit_item_effect import AuditItemEffect
from app.services.operations_service import OperationsService


def _operation_line(
    *,
    line_id: int,
    item_id: int | None,
    inventory_subject_id: int | None,
    qty: int,
    temporary_draft_payload: dict[str, object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=line_id,
        line_uuid=uuid4(),
        line_number=1,
        item_id=item_id,
        inventory_subject_id=inventory_subject_id,
        qty=qty,
        accepted_qty=0,
        lost_qty=0,
        temporary_draft_payload=temporary_draft_payload,
        item_name_snapshot=None,
        item_sku_snapshot=None,
        unit_name_snapshot=None,
        unit_symbol_snapshot=None,
        category_name_snapshot=None,
        batch=None,
        comment=None,
        source_item_name=None,
        source_item_sku=None,
        source_unit_name=None,
        source_category_name=None,
    )


def _submit_returns(operation):
    """submit_operation mock that returns a copy with revision_0 id set."""

    async def _side_effect(*, operation_id, submitted_by_user_id, expected_version=None):
        # `submitted_operation.current_revision_id = revision_0.id` happens before
        # `_write_captured_effects`, so the operation passed to the effect writer
        # must already expose the revision id and the same fields the service
        # touches downstream (effective_at, documents, short_id, origin).
        submitted = SimpleNamespace(
            id=operation.id,
            status="submitted",
            operation_type=operation.operation_type,
            site_id=operation.site_id,
            source_site_id=operation.source_site_id,
            destination_site_id=operation.destination_site_id,
            acceptance_required=operation.acceptance_required,
            issue_object_id=operation.issue_object_id,
            lines=operation.lines,
            effective_at=getattr(operation, "effective_at", None),
            documents=getattr(operation, "documents", []),
            short_id=getattr(operation, "short_id", None),
            origin=getattr(operation, "origin", "user"),
            current_revision_id=uuid4(),
        )
        return submitted

    return AsyncMock(side_effect=_side_effect)


def _build_uow(
    operation,
    *,
    balance_qty: Decimal | None = None,
    inventory_subjects_repo: SimpleNamespace | None = None,
    catalog_repo: SimpleNamespace | None = None,
):
    balances = SimpleNamespace(
        get_for_update=AsyncMock(return_value=SimpleNamespace(qty=balance_qty or Decimal("0"))),
        update_balance_quantity=AsyncMock(),
    )
    operations = SimpleNamespace(
        get_operation_by_id=AsyncMock(side_effect=[operation]),
        submit_operation=_submit_returns(operation),
    )
    asset_registers = SimpleNamespace(
        upsert_pending=AsyncMock(),
        upsert_lost=AsyncMock(),
        upsert_issued=AsyncMock(),
    )
    audit_events = SimpleNamespace(
        insert=AsyncMock(),
        # ADR-0028 §4.3: non-empty capture requires a configured hook. The mock
        # returns the same AuditItemEffect that was passed in so the service can
        # chain `written.append(await insert_effect(...))` without altering
        # observable behaviour.
        insert_effect=AsyncMock(side_effect=lambda effect: effect),
    )
    return SimpleNamespace(
        operations=operations,
        balances=balances,
        asset_registers=asset_registers,
        audit_events=audit_events,
        inventory_subjects=inventory_subjects_repo,
        catalog=catalog_repo,
        session=SimpleNamespace(flush=AsyncMock()),
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
        issue_object_id=None,
        effective_at=SimpleNamespace(isoformat=lambda: "2026-08-06T00:00:00+00:00"),
        documents=[],
        short_id="OP-RC",
        origin="user",
        creation_source="legacy",
        notes=None,
        lines=[_operation_line(line_id=1, item_id=101, inventory_subject_id=5001, qty=3)],
    )
    inventory_subjects = SimpleNamespace(
        get_or_create_for_item=AsyncMock(
            side_effect=lambda *, item_id: SimpleNamespace(id=item_id, item_id=item_id, subject_type="catalog_item", item=SimpleNamespace(name="X", sku="X")),
        ),
        get_by_id=AsyncMock(return_value=None),
    )
    uow = _build_uow(operation, inventory_subjects_repo=inventory_subjects)

    await OperationsService.submit_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    uow.audit_events.insert.assert_awaited_once()
    # Phase 1 / TZ-AUDIT_BACKEND_FOUNDATION: submit_operation now captures
    # the balance before/after for audit_item_effects in a single
    # get_for_update round-trip and writes the new qty directly to the
    # session — update_balance_quantity is no longer called per-line.
    uow.balances.get_for_update.assert_awaited_once_with(
        site_id=10,
        inventory_subject_id=5001,
    )
    # ADR-0028 §4.3: RECEIVE without acceptance_required writes one audit effect
    # row referencing the submit event id.
    uow.audit_events.insert_effect.assert_awaited_once()
    effect = uow.audit_events.insert_effect.await_args.args[0]
    assert isinstance(effect, AuditItemEffect)
    assert effect.effect_type == "receipt"
    assert effect.quantity_delta == Decimal("3")


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
        issue_object_id=77,
        effective_at=SimpleNamespace(isoformat=lambda: "2026-08-06T00:00:00+00:00"),
        documents=[],
        short_id="OP-IS",
        origin="user",
        creation_source="legacy",
        notes=None,
        lines=[_operation_line(line_id=1, item_id=101, inventory_subject_id=5001, qty=2)],
    )
    inventory_subjects = SimpleNamespace(
        get_or_create_for_item=AsyncMock(
            side_effect=lambda *, item_id: SimpleNamespace(id=item_id, item_id=item_id, subject_type="catalog_item", item=SimpleNamespace(name="X", sku="X")),
        ),
        get_by_id=AsyncMock(return_value=None),
    )
    uow = _build_uow(
        operation,
        balance_qty=Decimal("10"),
        inventory_subjects_repo=inventory_subjects,
    )

    await OperationsService.submit_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    uow.audit_events.insert.assert_awaited_once()
    uow.balances.get_for_update.assert_any_call(
        site_id=10, inventory_subject_id=5001,
    )
    uow.asset_registers.upsert_issued.assert_awaited_once_with(
        issue_object_id=77,
        inventory_subject_id=5001,
        qty_delta=Decimal("2"),
    )
    uow.audit_events.insert_effect.assert_awaited_once()
    effect = uow.audit_events.insert_effect.await_args.args[0]
    assert effect.effect_type == "issue"
    assert effect.quantity_delta == Decimal("-2")


@pytest.mark.asyncio
async def test_submit_receive_materializes_temporary_line_before_balance_update() -> None:
    line = _operation_line(
        line_id=1,
        item_id=None,
        inventory_subject_id=None,
        qty=3,
        temporary_draft_payload={
            "client_key": "tmp-1",
            "name": "Temporary cable",
            "sku": None,
            "unit_id": 11,
            "category_id": 22,
        },
    )
    operation = SimpleNamespace(
        id=uuid4(),
        status="draft",
        operation_type="RECEIVE",
        site_id=10,
        source_site_id=None,
        destination_site_id=None,
        acceptance_required=False,
        issue_object_id=None,
        effective_at=SimpleNamespace(isoformat=lambda: "2026-08-06T00:00:00+00:00"),
        documents=[],
        short_id="OP-RC",
        origin="user",
        creation_source="legacy",
        notes=None,
        lines=[line],
    )
    inventory_subjects = SimpleNamespace(
        get_or_create_for_item=AsyncMock(return_value=SimpleNamespace(id=9001, item_id=7001, subject_type="catalog_item", item=SimpleNamespace(name="Tmp", sku=None))),
        get_by_id=AsyncMock(return_value=None),
    )
    catalog = SimpleNamespace(
        create_item=AsyncMock(return_value=SimpleNamespace(id=7001)),
        get_item_by_id=AsyncMock(return_value=SimpleNamespace(id=7001, is_active=True)),
    )
    uow = _build_uow(
        operation,
        inventory_subjects_repo=inventory_subjects,
        catalog_repo=catalog,
    )

    await OperationsService.submit_operation(uow=uow, operation_id=operation.id, user_id=uuid4())

    uow.audit_events.insert.assert_awaited_once()
    catalog.create_item.assert_awaited_once()
    inventory_subjects.get_or_create_for_item.assert_awaited_once_with(item_id=7001)
    # Phase 1 / TZ-AUDIT_BACKEND_FOUNDATION: balance updates happen via
    # single-shot get_for_update + direct row mutation so the audit
    # capture sees the before/after quantity without a redundant re-lock.
    uow.balances.get_for_update.assert_awaited_once_with(
        site_id=10,
        inventory_subject_id=9001,
    )
    assert line.item_id == 7001
    assert line.inventory_subject_id == 9001
    assert line.temporary_draft_payload is None
    uow.audit_events.insert_effect.assert_awaited_once()
