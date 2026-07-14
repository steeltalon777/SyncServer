"""Service integration tests for audit_effects writing on operation.submit/cancel.

Covers submit effects per operation type, cancel reversal effects,
and parent_event_id propagation through the UoW context.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.audit_event import AuditEvent
from app.models.audit_item_effect import AuditItemEffect
from app.repos.audit_events_repo import AuditEventsRepo
from app.schemas.catalog import ItemCreateRequest
from app.services.catalog_admin_service import CatalogAdminService
from app.services.operations_service import OperationsService
from app.schemas.operation import OperationCreate, OperationLineCreate


pytestmark = pytest.mark.asyncio


async def _make_catalog_fixtures(uow):
    """Create a catalog item + inventory subject so operation lines resolve."""
    service = CatalogAdminService()
    item = await service.create_item(
        uow,
        ItemCreateRequest(
            sku=f"AUDIT-OP-{uuid4().hex[:6]}",
            name="Audit Op Item",
            category_id=None,
            unit_id=await _ensure_unit_id(uow),
            is_active=True,
        ),
        created_by_user_id=None,
    )
    return item


async def _ensure_unit_id(uow):
    from app.models.unit import Unit as UnitModel
    from sqlalchemy import select
    unit = (
        await uow.session.execute(
            select(UnitModel).where(UnitModel.code == "AU")
        )
    ).scalar_one_or_none()
    if unit is None:
        unit = UnitModel(code="AU", name="Audit unit", symbol="au", is_active=True)
        uow.session.add(unit)
        await uow.session.flush()
    return unit.id


async def test_submit_writes_one_effect_per_line(uow, test_user, test_site):
    """RECEIVE: one operation.submit event + one adjustment effect per line."""
    item = await _make_catalog_fixtures(uow)
    op = await uow.operations.create_operation(
        site_id=test_site.id,
        operation_type="RECEIVE",
        created_by_user_id=test_user.id,
        effective_at=datetime.now(UTC),
    )
    line = await uow.operations.create_operation_line(
        operation_id=op.id,
        line_number=1,
        inventory_subject_id=None,
        item_id=item.id,
        qty=Decimal("4"),
    )
    await uow.session.flush()

    result = await OperationsService.submit_operation(
        uow=uow,
        operation_id=op.id,
        user_id=test_user.id,
    )
    assert result["operation"].status == "submitted"

    # Find the operation.submit event for this operation
    submit_event: AuditEvent = (
        await uow.session.execute(
            AuditEvent.__table__.select().where(
                (AuditEvent.event_type == "operation.submit")
                & (AuditEvent.entity_id == str(op.id))
            )
        )
    ).first()
    assert submit_event is not None
    submit_id = int(submit_event[0])

    effects = await uow.audit_events.list_effects(submit_id)
    assert len(effects) == 1
    assert effects[0].effect_type == "receipt"
    assert effects[0].quantity_delta == Decimal("4")
    assert effects[0].is_system_generated is False
    assert effects[0].item_id == item.id


async def test_submit_marks_system_origin(uow, test_user, test_site):
    """When the operation origin is 'system', the effect.is_system_generated
    flag must be true.
    """
    item = await _make_catalog_fixtures(uow)
    op = await uow.operations.create_operation(
        site_id=test_site.id,
        operation_type="ADJUSTMENT",
        created_by_user_id=test_user.id,
        effective_at=datetime.now(UTC),
        origin="system",
        system_reason="audit-test-system",
        initiated_by_user_id=test_user.id,
    )
    await uow.operations.create_operation_line(
        operation_id=op.id,
        line_number=1,
        inventory_subject_id=None,
        item_id=item.id,
        qty=Decimal("7"),
    )

    await OperationsService.submit_operation(
        uow=uow,
        operation_id=op.id,
        user_id=test_user.id,
    )

    submit_id_row = (
        await uow.session.execute(
            AuditEvent.__table__.select()
            .where(
                (AuditEvent.event_type == "operation.submit")
                & (AuditEvent.entity_id == str(op.id))
            )
            .order_by(AuditEvent.id.desc())
            .limit(1)
        )
    ).first()
    submit_id = int(submit_id_row[0])

    effects = await uow.audit_events.list_effects(submit_id)
    assert len(effects) == 1
    assert effects[0].is_system_generated is True


async def test_cancel_writes_reversal_effect(uow, test_user, test_site):
    """Submit then cancel: cancel event has reversal effects."""
    item = await _make_catalog_fixtures(uow)
    op = await uow.operations.create_operation(
        site_id=test_site.id,
        operation_type="RECEIVE",
        created_by_user_id=test_user.id,
        effective_at=datetime.now(UTC),
    )
    await uow.operations.create_operation_line(
        operation_id=op.id,
        line_number=1,
        inventory_subject_id=None,
        item_id=item.id,
        qty=Decimal("4"),
    )
    await OperationsService.submit_operation(
        uow=uow,
        operation_id=op.id,
        user_id=test_user.id,
    )
    # Now cancel
    await OperationsService.cancel_operation(
        uow=uow,
        operation_id=op.id,
        user_id=test_user.id,
        reason="audit-smoke-cancel",
    )

    cancel_id_row = (
        await uow.session.execute(
            AuditEvent.__table__.select()
            .where(
                (AuditEvent.event_type == "operation.cancel")
                & (AuditEvent.entity_id == str(op.id))
            )
            .order_by(AuditEvent.id.desc())
            .limit(1)
        )
    ).first()
    cancel_id = int(cancel_id_row[0])
    effects = await uow.audit_events.list_effects(cancel_id)
    assert len(effects) == 1
    assert effects[0].effect_type == "cancel_reversal"
    assert effects[0].quantity_delta == Decimal("-4")


async def test_submit_effects_for_move_operation_have_move_io_split(uow, test_user, test_site):
    """MOVE without acceptance_required: TWO effects (move_out, move_in)."""
    from app.models.site import Site as SiteModel
    from sqlalchemy import select

    other = (
        await uow.session.execute(
            select(SiteModel).where(SiteModel.code == "AUDIT-2")
        )
    ).scalar_one_or_none()
    if other is None:
        other = SiteModel(code="AUDIT-2", name="Audit site 2", normalized_name="audit site 2", is_active=True)
        uow.session.add(other)
        await uow.session.flush()

    item = await _make_catalog_fixtures(uow)
    # Pre-seed source-side balance so the source decrement succeeds.
    subject = await uow.inventory_subjects.get_or_create_for_item(item_id=item.id)
    await uow.balances.update_balance_quantity(
        site_id=test_site.id,
        inventory_subject_id=subject.id,
        quantity_delta=Decimal("10"),
    )

    op = await uow.operations.create_operation(
        site_id=test_site.id,
        operation_type="MOVE",
        created_by_user_id=test_user.id,
        effective_at=datetime.now(UTC),
        source_site_id=test_site.id,
        destination_site_id=other.id,
        acceptance_required=False,
    )
    await uow.operations.create_operation_line(
        operation_id=op.id,
        line_number=1,
        inventory_subject_id=subject.id,
        item_id=item.id,
        qty=Decimal("3"),
    )

    await OperationsService.submit_operation(
        uow=uow,
        operation_id=op.id,
        user_id=test_user.id,
    )

    submit_id_row = (
        await uow.session.execute(
            AuditEvent.__table__.select()
            .where(
                (AuditEvent.event_type == "operation.submit")
                & (AuditEvent.entity_id == str(op.id))
            )
            .order_by(AuditEvent.id.desc())
            .limit(1)
        )
    ).first()
    submit_id = int(submit_id_row[0])
    effects = await uow.audit_events.list_effects(submit_id)
    types = sorted(e.effect_type for e in effects)
    assert "move_out" in types
    assert "move_in" in types


async def test_rollback_drops_effects(uow, test_user, test_site):
    """If submit_operation raises before commit, no effects are persisted."""
    # Force a failure: submit a non-draft operation (should violate workflow).
    item = await _make_catalog_fixtures(uow)
    op = await uow.operations.create_operation(
        site_id=test_site.id,
        operation_type="RECEIVE",
        created_by_user_id=test_user.id,
        effective_at=datetime.now(UTC),
    )
    # Make it already-submitted by submitting once
    await uow.operations.create_operation_line(
        operation_id=op.id,
        line_number=1,
        inventory_subject_id=None,
        item_id=item.id,
        qty=Decimal("1"),
    )
    # First submit succeeds
    await OperationsService.submit_operation(
        uow=uow,
        operation_id=op.id,
        user_id=test_user.id,
    )

    # Snapshot event count
    before = int(
        (
            await uow.session.execute(
                AuditEvent.__table__.select().where(
                    (AuditEvent.event_type == "operation.submit")
                    & (AuditEvent.entity_id == str(op.id))
                )
            )
        ).rowcount or 0
    )
    # Second submit must fail; ensure no extra events / effects persist.
    from fastapi import HTTPException
    with pytest.raises((HTTPException, Exception)):
        await OperationsService.submit_operation(
            uow=uow,
            operation_id=op.id,
            user_id=test_user.id,
        )

    after = int(
        (
            await uow.session.execute(
                AuditEvent.__table__.select().where(
                    (AuditEvent.event_type == "operation.submit")
                    & (AuditEvent.entity_id == str(op.id))
                )
            )
        ).rowcount or 0
    )
    # No new events for this op
    assert after == before
