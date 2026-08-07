"""A-4 / ADR-0028 §4 acceptance/lost audit completeness tests.

Each `accept_operation_lines` non-zero action and each `resolve_lost_asset`
action must produce a per-action audit event. Accepted / found / return
actions must additionally produce a warehouse `audit_item_effect` with
`effect_type='acceptance'`. `mark_lost` and `write_off` are observable
through audit events only — they must NOT mutate warehouse balances and
must NOT create `audit_item_effect` rows.

Tests run inside the disposable `session_factory` schema from
`tests/conftest.py` and never leave the schema.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Iterable
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.audit_event import AuditEvent
from app.models.audit_item_effect import AuditItemEffect
from app.models.balance import Balance
from app.models.inventory_subject import InventorySubject
from app.models.item import Item
from app.schemas.asset_register import OperationAcceptLinePayload
from app.services.catalog_admin_service import CatalogAdminService
from app.services.operations_service import OperationsService
from app.schemas.catalog import ItemCreateRequest
from app.schemas.operation import (
    OperationCreate,
    OperationLineCreate,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


async def _ensure_unit_id(uow) -> int:
    from app.models.unit import Unit as UnitModel

    unit = (
        await uow.session.execute(
            select(UnitModel).where(UnitModel.code == "A4-PCS")
        )
    ).scalar_one_or_none()
    if unit is None:
        unit = UnitModel(
            code="A4-PCS",
            name="A4 Pieces",
            symbol="a4pc",
            is_active=True,
        )
        uow.session.add(unit)
        await uow.session.flush()
    return int(unit.id)


async def _ensure_category_id(uow) -> int:
    from app.models.category import Category as CategoryModel

    category = (
        await uow.session.execute(
            select(CategoryModel).where(CategoryModel.code == "A4-CAT")
        )
    ).scalar_one_or_none()
    if category is None:
        category = CategoryModel(
            code="A4-CAT",
            name="A4 Category",
            normalized_name="a4 category",
            is_active=True,
        )
        uow.session.add(category)
        await uow.session.flush()
    return int(category.id)


async def _create_item(uow) -> Item:
    service = CatalogAdminService()
    item = await service.create_item(
        uow,
        ItemCreateRequest(
            sku=f"A4-{uuid4().hex[:6]}",
            name="A4 Acceptance Item",
            category_id=await _ensure_category_id(uow),
            unit_id=await _ensure_unit_id(uow),
            is_active=True,
        ),
    )
    return item


async def _create_receive_with_acceptance(
    uow,
    *,
    user,
    site,
    item: Item,
    qty: Decimal,
) -> tuple[object, object]:
    op = await uow.operations.create_operation(
        site_id=site.id,
        operation_type="RECEIVE",
        created_by_user_id=user.id,
        effective_at=datetime.now(UTC),
        acceptance_required=True,
    )
    line = await uow.operations.create_operation_line(
        operation_id=op.id,
        line_number=1,
        inventory_subject_id=None,
        item_id=item.id,
        qty=qty,
    )
    await uow.operations.update_operation_line_progress(
        operation_line_id=line.id,
        accepted_delta=Decimal("0"),
        lost_delta=Decimal("0"),
    )
    return op, line


async def _submit(uow, op_id, user) -> None:
    await OperationsService.submit_operation(
        uow=uow,
        operation_id=op_id,
        user_id=user.id,
    )


async def _event_ids(
    uow, *, event_type: str, entity_id: str
) -> list[int]:
    rows = (
        await uow.session.execute(
            select(AuditEvent.id).where(
                AuditEvent.event_type == event_type,
                AuditEvent.entity_id == entity_id,
            ).order_by(AuditEvent.id.asc())
        )
    ).scalars().all()
    return [int(r) for r in rows]


async def _effect_rows(
    uow, *, event_id: int
) -> list[AuditItemEffect]:
    return list(
        (
            await uow.session.execute(
                select(AuditItemEffect).where(
                    AuditItemEffect.audit_event_id == event_id,
                )
            )
        ).scalars().all()
    )


# ---------------------------------------------------------------------------
# A-4.1: accept qty>0 → line_accepted event + acceptance effect
# ---------------------------------------------------------------------------


async def test_accept_qty_writes_line_accepted_event_and_effect(
    uow, test_user, test_site
):
    item = await _create_item(uow)
    op, line = await _create_receive_with_acceptance(
        uow, user=test_user, site=test_site, item=item, qty=Decimal("10"),
    )
    await _submit(uow, op.id, test_user)

    result = await OperationsService.accept_operation_lines(
        uow,
        operation_id=op.id,
        user_id=test_user.id,
        line_updates=[
            OperationAcceptLinePayload(line_id=line.id, accepted_qty=4, lost_qty=0)
        ],
    )
    assert result["operation"].status == "submitted"

    line_event_ids = await _event_ids(
        uow,
        event_type="operation.line_accepted",
        entity_id=str(line.id),
    )
    assert len(line_event_ids) == 1, line_event_ids
    effects = await _effect_rows(uow, event_id=line_event_ids[0])
    assert len(effects) == 1
    eff = effects[0]
    assert eff.effect_type == "acceptance"
    assert Decimal(eff.quantity_delta) == Decimal("4")
    assert eff.operation_id == op.id
    assert eff.inventory_subject_id == line.inventory_subject_id
    assert Decimal(eff.quantity_after) - Decimal(eff.quantity_before) == Decimal("4")


# ---------------------------------------------------------------------------
# A-4.2: mark_lost qty>0 → line_mark_lost event, NO warehouse effect
# ---------------------------------------------------------------------------


async def test_mark_lost_writes_event_without_warehouse_effect(
    uow, test_user, test_site
):
    item = await _create_item(uow)
    op, line = await _create_receive_with_acceptance(
        uow, user=test_user, site=test_site, item=item, qty=Decimal("10"),
    )
    await _submit(uow, op.id, test_user)

    result = await OperationsService.accept_operation_lines(
        uow,
        operation_id=op.id,
        user_id=test_user.id,
        line_updates=[
            OperationAcceptLinePayload(line_id=line.id, accepted_qty=0, lost_qty=3)
        ],
    )
    assert result["operation"].status == "submitted"

    mark_lost_event_ids = await _event_ids(
        uow,
        event_type="operation.line_mark_lost",
        entity_id=str(line.id),
    )
    assert len(mark_lost_event_ids) == 1
    effects = await _effect_rows(uow, event_id=mark_lost_event_ids[0])
    assert effects == []

    # global audit_item_effects must not include a row for this operation
    # tagged 'acceptance' from the mark_lost action (only the future
    # resolve events will produce one). We assert by inventory_subject_id
    # because audit_item_effects has no operation_line_id column.
    all_effects_for_subject = (
        await uow.session.execute(
            select(AuditItemEffect).where(
                AuditItemEffect.inventory_subject_id == line.inventory_subject_id
            )
        )
    ).scalars().all()
    assert all(e.effect_type != "acceptance" for e in all_effects_for_subject), (
        "mark_lost must not create an acceptance warehouse effect"
    )


# ---------------------------------------------------------------------------
# A-4.3: mixed accept+lost in one payload → two events, only accept has effect
# ---------------------------------------------------------------------------


async def test_mixed_accept_and_lost_creates_two_events_one_effect(
    uow, test_user, test_site
):
    item = await _create_item(uow)
    op, line = await _create_receive_with_acceptance(
        uow, user=test_user, site=test_site, item=item, qty=Decimal("10"),
    )
    await _submit(uow, op.id, test_user)

    await OperationsService.accept_operation_lines(
        uow,
        operation_id=op.id,
        user_id=test_user.id,
        line_updates=[
            OperationAcceptLinePayload(line_id=line.id, accepted_qty=4, lost_qty=3)
        ],
    )

    accepted_ids = await _event_ids(
        uow, event_type="operation.line_accepted", entity_id=str(line.id),
    )
    lost_ids = await _event_ids(
        uow, event_type="operation.line_mark_lost", entity_id=str(line.id),
    )
    assert len(accepted_ids) == 1
    assert len(lost_ids) == 1

    accept_effects = await _effect_rows(uow, event_id=accepted_ids[0])
    lost_effects = await _effect_rows(uow, event_id=lost_ids[0])
    assert len(accept_effects) == 1
    assert Decimal(accept_effects[0].quantity_delta) == Decimal("4")
    assert lost_effects == []


# ---------------------------------------------------------------------------
# A-4.4: zero payload (0/0) → no events
# ---------------------------------------------------------------------------


async def test_zero_payload_creates_no_events(uow, test_user, test_site):
    item = await _create_item(uow)
    op, line = await _create_receive_with_acceptance(
        uow, user=test_user, site=test_site, item=item, qty=Decimal("5"),
    )
    await _submit(uow, op.id, test_user)

    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        await OperationsService.accept_operation_lines(
            uow,
            operation_id=op.id,
            user_id=test_user.id,
            line_updates=[
                OperationAcceptLinePayload(line_id=line.id, accepted_qty=0, lost_qty=0)
            ],
        )

    accepted = await _event_ids(
        uow, event_type="operation.line_accepted", entity_id=str(line.id),
    )
    lost = await _event_ids(
        uow, event_type="operation.line_mark_lost", entity_id=str(line.id),
    )
    assert accepted == []
    assert lost == []


# ---------------------------------------------------------------------------
# A-4.5: resolve_lost_asset(found_to_destination) → line_lost_resolved + effect
# ---------------------------------------------------------------------------


async def _seed_lost_row(
    uow, *, user, site, item: Item, qty: Decimal
) -> tuple[object, object]:
    op, line = await _create_receive_with_acceptance(
        uow, user=user, site=site, item=item, qty=qty,
    )
    await _submit(uow, op.id, user)
    # mark all qty as lost to seed a non-zero lost register
    await OperationsService.accept_operation_lines(
        uow,
        operation_id=op.id,
        user_id=user.id,
        line_updates=[
            OperationAcceptLinePayload(line_id=line.id, accepted_qty=0, lost_qty=qty)
        ],
    )
    return op, line


async def test_resolve_lost_found_to_destination_writes_event_and_effect(
    uow, test_user, test_site
):
    item = await _create_item(uow)
    op, line = await _seed_lost_row(
        uow, user=test_user, site=test_site, item=item, qty=Decimal("5"),
    )

    # subject id is known at this point
    subject_id = int(line.inventory_subject_id)
    balance_before_row = await uow.balances.get_for_update(
        site_id=test_site.id, inventory_subject_id=subject_id
    )
    qty_before = Decimal(getattr(balance_before_row, "qty", 0) or 0)

    result = await OperationsService.resolve_lost_asset(
        uow,
        operation_line_id=line.id,
        action="found_to_destination",
        qty=Decimal("2"),
        user_id=test_user.id,
        note="found by inventory",
        responsible_recipient_id=None,
    )
    assert result["status"] == "ok"

    event_ids = await _event_ids(
        uow, event_type="operation.line_lost_resolved", entity_id=str(line.id),
    )
    assert len(event_ids) == 1
    event_row = (
        await uow.session.execute(
            select(AuditEvent).where(AuditEvent.id == event_ids[0])
        )
    ).scalar_one()
    assert (event_row.changes or {}).get("action_type") == "found_to_destination"

    effects = await _effect_rows(uow, event_id=event_ids[0])
    assert len(effects) == 1
    eff = effects[0]
    assert eff.effect_type == "acceptance"
    assert Decimal(eff.quantity_delta) == Decimal("2")
    assert eff.site_id == test_site.id
    assert Decimal(eff.quantity_after) - Decimal(eff.quantity_before) == Decimal("2")
    assert Decimal(eff.quantity_before) == qty_before


async def test_resolve_lost_return_to_source_writes_event_and_effect(
    uow, test_user, test_site, secondary_site
):
    # Use MOVE+acceptance (without acceptance_required) so source_site_id
    # is populated in the lost row. We pre-seed source balance to satisfy
    # the submit-time stock check, and we don't pre-seed destination so
    # the rollback stays minimal.
    item = await _create_item(uow)
    subject = await uow.inventory_subjects.get_or_create_for_item(item_id=item.id)
    await uow.balances.update_balance_quantity(
        site_id=test_site.id,
        inventory_subject_id=subject.id,
        quantity_delta=Decimal("5"),
    )

    op = await uow.operations.create_operation(
        site_id=test_site.id,
        operation_type="MOVE",
        created_by_user_id=test_user.id,
        effective_at=datetime.now(UTC),
        source_site_id=test_site.id,
        destination_site_id=secondary_site.id,
        acceptance_required=False,
    )
    line = await uow.operations.create_operation_line(
        operation_id=op.id,
        line_number=1,
        inventory_subject_id=subject.id,
        item_id=item.id,
        qty=Decimal("5"),
    )
    await _submit(uow, op.id, test_user)

    # After MOVE submission, the qty lives on destination_site_id.
    # To trigger a "lost" state we cannot use accept_operation_lines
    # (no acceptance_required), so we directly create a lost row through
    # the underlying repo. This mirrors the realistic flow that occurs
    # when an offline client reports a discrepancy.
    from app.models.asset_register import LostAssetBalance

    lost = LostAssetBalance(
        operation_id=op.id,
        operation_line_id=line.id,
        site_id=secondary_site.id,
        source_site_id=test_site.id,
        inventory_subject_id=subject.id,
        qty=Decimal("3"),
    )
    uow.session.add(lost)
    await uow.session.flush()

    result = await OperationsService.resolve_lost_asset(
        uow,
        operation_line_id=line.id,
        action="return_to_source",
        qty=Decimal("3"),
        user_id=test_user.id,
        note="returned to source",
        responsible_recipient_id=None,
    )
    assert result["status"] == "ok"

    event_ids = await _event_ids(
        uow, event_type="operation.line_lost_resolved", entity_id=str(line.id),
    )
    assert len(event_ids) == 1
    event_row = (
        await uow.session.execute(
            select(AuditEvent).where(AuditEvent.id == event_ids[0])
        )
    ).scalar_one()
    assert (event_row.changes or {}).get("action_type") == "return_to_source"

    effects = await _effect_rows(uow, event_id=event_ids[0])
    assert len(effects) == 1
    eff = effects[0]
    assert eff.effect_type == "acceptance"
    assert eff.site_id == test_site.id
    assert Decimal(eff.quantity_delta) == Decimal("3")


async def test_resolve_lost_write_off_writes_event_without_effect(
    uow, test_user, test_site
):
    item = await _create_item(uow)
    op, line = await _seed_lost_row(
        uow, user=test_user, site=test_site, item=item, qty=Decimal("5"),
    )

    result = await OperationsService.resolve_lost_asset(
        uow,
        operation_line_id=line.id,
        action="write_off",
        qty=Decimal("2"),
        user_id=test_user.id,
        note="written off",
        responsible_recipient_id=None,
    )
    assert result["status"] == "ok"

    event_ids = await _event_ids(
        uow, event_type="operation.line_lost_resolved", entity_id=str(line.id),
    )
    assert len(event_ids) == 1
    effects = await _effect_rows(uow, event_id=event_ids[0])
    assert effects == [], "write_off must not create a warehouse effect"

    # confirm balances did not move
    subject_id = int(line.inventory_subject_id)
    balance_row = await uow.balances.get_for_update(
        site_id=test_site.id, inventory_subject_id=subject_id
    )
    assert Decimal(getattr(balance_row, "qty", 0) or 0) == Decimal("0")


# ---------------------------------------------------------------------------
# A-4.7: _write_captured_effects fail-closed on non-empty capture without hook
# ---------------------------------------------------------------------------


async def test_write_captured_effects_raises_when_hook_missing(uow):
    """ADR-0028 §4.3: non-empty capture without audit_events.insert_effect
    is an invariant violation and must abort the UoW.
    """
    from app.services.operations_service import OperationsService as _OS

    # Build a stand-in uow whose audit_events attribute has no insert_effect
    class _NoHookRepo:
        pass

    class _NoHookUow:
        audit_events = _NoHookRepo()
        inventory_subjects = None  # skip snapshot enrichment

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    capture: list[dict] = [
        {
            "site_id": 1,
            "inventory_subject_id": 1,
            "quantity_before": Decimal("0"),
            "quantity_delta": Decimal("1"),
            "quantity_after": Decimal("1"),
            "effect_type": "acceptance",
            "operation_line_id": 1,
        }
    ]
    with pytest.raises(RuntimeError, match="audit_items_effects hook missing"):
        await _OS._write_captured_effects(
            _NoHookUow(),
            capture=capture,
            audit_event_id=999,
            operation_id=uuid4(),
            is_system_generated=False,
        )

    # empty capture must remain a no-op (no raise, no insert)
    written = await _OS._write_captured_effects(
        _NoHookUow(),
        capture=[],
        audit_event_id=999,
        operation_id=uuid4(),
        is_system_generated=False,
    )
    assert written == []


# ---------------------------------------------------------------------------
# A-4.8: repeated accepted call must not double-count when rejected by workflow
# ---------------------------------------------------------------------------


async def test_repeated_accept_after_rejection_writes_no_extra_event(
    uow, test_user, test_site
):
    item = await _create_item(uow)
    op, line = await _create_receive_with_acceptance(
        uow, user=test_user, site=test_site, item=item, qty=Decimal("2"),
    )
    await _submit(uow, op.id, test_user)

    # First call: accepts 1 of 2
    await OperationsService.accept_operation_lines(
        uow,
        operation_id=op.id,
        user_id=test_user.id,
        line_updates=[
            OperationAcceptLinePayload(line_id=line.id, accepted_qty=1, lost_qty=0)
        ],
    )
    accepted_first = await _event_ids(
        uow, event_type="operation.line_accepted", entity_id=str(line.id),
    )
    assert len(accepted_first) == 1

    # Second call: zero payload is rejected by the service, so no event.
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        await OperationsService.accept_operation_lines(
            uow,
            operation_id=op.id,
            user_id=test_user.id,
            line_updates=[
                OperationAcceptLinePayload(line_id=line.id, accepted_qty=0, lost_qty=0)
            ],
        )
    accepted_second = await _event_ids(
        uow, event_type="operation.line_accepted", entity_id=str(line.id),
    )
    assert len(accepted_second) == 1, "rejected call must not create a duplicate"
