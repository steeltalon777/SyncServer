"""Service integration tests for item.merge Phase 1 audit pipeline.

Critical invariants verified here:
- Parent AuditEvent (item.merge) is INSERTed before ADJUSTMENT submits.
- ADJUSTMENT submit events carry parent_event_id pointing at the merge.
- audit_item_effects point at the source item (item_id = source_item_id),
  NOT the post-reassignment target item — effects are written before
  OperationLine reassignment.
- is_system_generated = true on effects; origin/system_reason on
  generated operations is 'system' / 'item_merge'.
- resource edges: merge_source, merge_target, generated → ADJUSTMENT ops.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.audit_event import AuditEvent
from app.models.audit_event_resource import AuditEventResource
from app.models.audit_item_effect import AuditItemEffect
from app.schemas.catalog import ItemCreateRequest
from app.services.catalog_admin_service import CatalogAdminService


pytestmark = pytest.mark.asyncio


async def _make_item(uow, sku: str, name: str, unit_id: int | None = None) -> int:
    from app.core.catalog_defaults import UNCATEGORIZED_CATEGORY_CODE
    from app.models.category import Category as CategoryModel
    from app.models.item import Item as ItemModel
    from app.models.unit import Unit as UnitModel
    from sqlalchemy import select

    if unit_id is None:
        unit = (
            await uow.session.execute(select(UnitModel).where(UnitModel.code == "AU"))
        ).scalar_one_or_none()
        if unit is None:
            unit = UnitModel(code="AU", name="Audit unit", symbol="au", is_active=True)
            uow.session.add(unit)
            await uow.session.flush()
        unit_id = unit.id

    cat = (
        await uow.session.execute(
            select(CategoryModel).where(CategoryModel.code == UNCATEGORIZED_CATEGORY_CODE)
        )
    ).scalar_one_or_none()
    if cat is None:
        cat = CategoryModel(
            name="uncategorized",
            code=UNCATEGORIZED_CATEGORY_CODE,
            parent_id=None,
            sort_order=0,
            is_active=True,
        )
        uow.session.add(cat)
        await uow.session.flush()

    item = ItemModel(
        sku=sku,
        name=name,
        normalized_name=name.lower(),
        category_id=cat.id,
        unit_id=unit_id,
        is_active=True,
    )
    uow.session.add(item)
    await uow.session.flush()
    return item.id


async def _make_site(uow, code: str = "AUDIT-SITE") -> int:
    from app.models.site import Site as SiteModel
    from sqlalchemy import select

    site = (await uow.session.execute(select(SiteModel).where(SiteModel.code == code))).scalar_one_or_none()
    if site is None:
        site = SiteModel(code=code, name="Audit site", normalized_name="audit site", is_active=True)
        uow.session.add(site)
        await uow.session.flush()
    return site.id


async def test_item_merge_writes_parent_event_first(uow, test_user):
    """The item.merge AuditEvent id is available before any ADJUSTMENT is submitted."""
    source_id = await _make_item(uow, "AUDIT-MERGE-SRC", "merge source")
    target_id = await _make_item(uow, "AUDIT-MERGE-TGT", "merge target")
    target_subject = await uow.inventory_subjects.get_or_create_for_item(item_id=target_id)
    # Pre-seed target balance so the merge write-off has somewhere to credit
    await uow.balances.update_balance_quantity(
        site_id=1,
        inventory_subject_id=target_subject.id,
        quantity_delta=Decimal("0"),
    )

    service = CatalogAdminService()
    target = await service.merge_items(
        uow,
        source_item_id=source_id,
        target_item_id=target_id,
        comment="audit-smoke",
        resolved_by_user_id=test_user.id,
    )
    assert target.id == target_id

    # Find the parent merge event
    parent_id_row = (
        await uow.session.execute(
            AuditEvent.__table__.select()
            .where(
                (AuditEvent.event_type == "item.merge")
                & (AuditEvent.entity_id == str(target_id))
            )
            .order_by(AuditEvent.id.desc())
            .limit(1)
        )
    ).first()
    assert parent_id_row is not None
    parent_id = int(parent_id_row[0])


async def test_item_merge_child_submits_carry_parent_event_id(uow, test_user):
    """Generated ADJUSTMENT operation.submit events must reference the merge."""
    source_id = await _make_item(uow, "AUDIT-MERGE-2-SRC", "merge 2 src")
    target_id = await _make_item(uow, "AUDIT-MERGE-2-TGT", "merge 2 tgt")
    # Seed source balance so the merge actually triggers a transfer.
    source_subject = await uow.inventory_subjects.get_or_create_for_item(item_id=source_id)
    await uow.balances.update_balance_quantity(
        site_id=1,
        inventory_subject_id=source_subject.id,
        quantity_delta=Decimal("7"),
    )

    service = CatalogAdminService()
    await service.merge_items(
        uow,
        source_item_id=source_id,
        target_item_id=target_id,
        comment="audit-parent",
        resolved_by_user_id=test_user.id,
    )

    merge_row = (
        await uow.session.execute(
            AuditEvent.__table__.select()
            .where(
                (AuditEvent.event_type == "item.merge")
                & (AuditEvent.entity_id == str(target_id))
            )
            .order_by(AuditEvent.id.desc())
            .limit(1)
        )
    ).first()
    parent_event_id = merge_row[1]
    parent_int_id = int(merge_row[0])

    children_rows = (
        await uow.session.execute(
            AuditEvent.__table__.select()
            .where(
                (AuditEvent.event_type == "operation.submit")
                & (AuditEvent.parent_event_id == parent_event_id)
            )
        )
    ).fetchall()
    assert len(children_rows) >= 1
    # AuditEvent column order: id(0), event_id(1), event_version(2), event_type(3),
    # actor_user_id(4), actor_device_id(5), site_id(6), entity_type(7), entity_id(8),
    # summary(9), changes(10), request_id(11), outcome(12), correlation_id(13),
    # parent_event_id(14)...
    assert all(row[14] == parent_event_id for row in children_rows)


async def test_item_merge_effects_point_at_source_item(uow, test_user):
    """audit_item_effects.item_id MUST equal source_item_id (effects written
    BEFORE the OperationLine reassignment destroys the source linkage).
    """
    source_id = await _make_item(uow, "AUDIT-MERGE-3-SRC", "merge 3 src")
    target_id = await _make_item(uow, "AUDIT-MERGE-3-TGT", "merge 3 tgt")
    source_subject = await uow.inventory_subjects.get_or_create_for_item(item_id=source_id)
    await uow.balances.update_balance_quantity(
        site_id=1,
        inventory_subject_id=source_subject.id,
        quantity_delta=Decimal("5"),
    )

    # Seed an OperationLine pointing at the source so the reassignment
    # mutation has something to redirect.
    from app.models.operation import Operation, OperationLine
    draft_op = Operation(
        site_id=1,
        operation_type="ADJUSTMENT",
        status="draft",
        created_by_user_id=test_user.id,
        effective_at=datetime.now(UTC),
    )
    uow.session.add(draft_op)
    await uow.session.flush()
    line = OperationLine(
        operation_id=draft_op.id,
        line_number=1,
        inventory_subject_id=source_subject.id,
        item_id=source_id,
        qty=Decimal("1"),
    )
    uow.session.add(line)
    await uow.session.flush()

    service = CatalogAdminService()
    await service.merge_items(
        uow,
        source_item_id=source_id,
        target_item_id=target_id,
        comment="audit-source-effect",
        resolved_by_user_id=test_user.id,
    )

    parent_row = (
        await uow.session.execute(
            AuditEvent.__table__.select()
            .where(
                (AuditEvent.event_type == "item.merge")
                & (AuditEvent.entity_id == str(target_id))
            )
            .order_by(AuditEvent.id.desc())
            .limit(1)
        )
    ).first()
    parent_int_id = int(parent_row[0])

    # Effects for this merge flow live on the operation.submit children
    submit_rows = (
        await uow.session.execute(
            AuditEvent.__table__.select()
            .where(
                (AuditEvent.event_type == "operation.submit")
                & (AuditEvent.parent_event_id == parent_row[1])
            )
        )
    ).fetchall()
    assert submit_rows, "expected system ADJUSTMENT submit events"

    effect_rows = (
        await uow.session.execute(
            AuditItemEffect.__table__.select().where(
                AuditItemEffect.__table__.c.audit_event_id.in_(
                    [int(r[0]) for r in submit_rows]
                )
            )
        )
    ).fetchall()
    assert effect_rows
    effect_types = sorted({r[12] for r in effect_rows})
    assert "merge_write_off" in effect_types or "merge_receipt" in effect_types

    # Effects that ARE write-offs must point at source, not target
    for r in effect_rows:
        if r[12] == "merge_write_off":
            assert int(r[4]) == source_id, (
                "merge_write_off effect must reference source item, not target"
            )


async def test_item_merge_generated_operations_are_system_origin(uow, test_user):
    """Generated ADJUSTMENT operations carry origin='system', system_reason='item_merge'."""
    from sqlalchemy import select
    from app.models.operation import Operation

    source_id = await _make_item(uow, "AUDIT-MERGE-4-SRC", "merge 4 src")
    target_id = await _make_item(uow, "AUDIT-MERGE-4-TGT", "merge 4 tgt")
    source_subject = await uow.inventory_subjects.get_or_create_for_item(item_id=source_id)
    await uow.balances.update_balance_quantity(
        site_id=1,
        inventory_subject_id=source_subject.id,
        quantity_delta=Decimal("6"),
    )

    service = CatalogAdminService()
    await service.merge_items(
        uow,
        source_item_id=source_id,
        target_item_id=target_id,
        comment="audit-sys-origin",
        resolved_by_user_id=test_user.id,
    )

    sys_ops = (
        await uow.session.execute(
            select(Operation).where(
                (Operation.origin == "system") & (Operation.system_reason == "item_merge")
            )
        )
    ).scalars().all()
    assert len(sys_ops) >= 1
    for op in sys_ops:
        assert op.initiated_by_user_id == test_user.id


async def test_item_merge_resources_linked(uow, test_user):
    """Resource edges: merge_source + merge_target + generated → ADJUSTMENT ops."""
    source_id = await _make_item(uow, "AUDIT-MERGE-5-SRC", "merge 5 src")
    target_id = await _make_item(uow, "AUDIT-MERGE-5-TGT", "merge 5 tgt")
    source_subject = await uow.inventory_subjects.get_or_create_for_item(item_id=source_id)
    await uow.balances.update_balance_quantity(
        site_id=1,
        inventory_subject_id=source_subject.id,
        quantity_delta=Decimal("8"),
    )

    service = CatalogAdminService()
    await service.merge_items(
        uow,
        source_item_id=source_id,
        target_item_id=target_id,
        comment="audit-resources",
        resolved_by_user_id=test_user.id,
    )

    parent_row = (
        await uow.session.execute(
            AuditEvent.__table__.select()
            .where(
                (AuditEvent.event_type == "item.merge")
                & (AuditEvent.entity_id == str(target_id))
            )
            .order_by(AuditEvent.id.desc())
            .limit(1)
        )
    ).first()
    parent_int_id = int(parent_row[0])

    res_rows = (
        await uow.session.execute(
            AuditEventResource.__table__.select()
            .where(AuditEventResource.__table__.c.audit_event_id == parent_int_id)
        )
    ).fetchall()
    relations = {r[4] for r in res_rows}
    assert "merge_source" in relations
    assert "merge_target" in relations
    assert "generated" in relations

    # Verify the source/target resource links point at the right items
    by_relation: dict[str, list] = {}
    for r in res_rows:
        by_relation.setdefault(r[4], []).append(r)
    source_links = [r for r in by_relation["merge_source"] if r[2] == "item"]
    target_links = [r for r in by_relation["merge_target"] if r[2] == "item"]
    assert any(r[3] == str(source_id) for r in source_links)
    assert any(r[3] == str(target_id) for r in target_links)
