"""Repository tests for Phase 1 audit storage surface.

Covers AuditEventsRepo.insert / insert_resource / insert_effect,
the new filter shapes, get_effects_by_item / get_effects_by_subject,
list_by_parent_event_id / list_by_correlation_id, and the append-only
invariant via FK policy (RESTRICT blocks dependent-resource deletion).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, UTC
from uuid import uuid4, UUID

import pytest
from sqlalchemy import select, text

from app.models.audit_event import AuditEvent
from app.models.audit_event_resource import AuditEventResource
from app.models.audit_item_effect import AuditItemEffect
from app.models.item import Item
from app.models.inventory_subject import InventorySubject
from app.repos.audit_events_repo import AuditEventsRepo


pytestmark = pytest.mark.asyncio




async def _make_item(uow, sku, name, site_id: int | None = None):
    from app.core.catalog_defaults import UNCATEGORIZED_CATEGORY_CODE
    from app.models.category import Category as CategoryModel
    from app.models.item import Item as ItemModel
    from app.models.site import Site as SiteModel
    from app.models.unit import Unit as UnitModel

    if site_id is None:
        site = (
            await uow.session.execute(
                select(SiteModel).where(SiteModel.code == "AUDIT")
            )
        ).scalar_one_or_none()
        if site is None:
            site = SiteModel(code="AUDIT", name="Audit site", normalized_name="audit site", is_active=True)
            uow.session.add(site)
            await uow.session.flush()
        site_id = site.id

    unit = (
        await uow.session.execute(
            select(UnitModel).where(UnitModel.code == "AU")
        )
    ).scalar_one_or_none()
    if unit is None:
        unit = UnitModel(code="AU", name="Audit unit", symbol="au", is_active=True)
        uow.session.add(unit)
        await uow.session.flush()

    cat = (
        await uow.session.execute(
            select(CategoryModel).where(CategoryModel.code == UNCATEGORIZED_CATEGORY_CODE)
        )
    ).scalar_one_or_none()
    if cat is None:
        cat = CategoryModel(
            name='uncategorized',
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
        unit_id=unit.id,
        is_active=True,
    )
    uow.session.add(item)
    await uow.session.flush()
    return item, site_id


async def _make_event(uow, *, event_type="test.event", changes=None) -> AuditEvent:
    event = AuditEvent(
        event_type=event_type,
        event_version=2,
        actor_user_id=None,
        entity_type="test",
        entity_id="1",
        summary="repo test event",
        changes=changes or {"k": "v"},
        outcome="success",
    )
    return await uow.audit_events.insert(event)


async def test_insert_event_with_v2_fields(uow):
    """Phase 1 v2 surface accepted by insert."""
    repo: AuditEventsRepo = uow.audit_events
    event = AuditEvent(
        event_type="audit.repo.insert_v2",
        event_version=2,
        actor_user_id=None,
        entity_type="catalog",
        entity_id="42",
        summary="v2 smoke",
        outcome="success",
        correlation_id="corr-1",
        parent_event_id=None,
        source_client="web",
        actor_username_snapshot="root",
    )
    inserted = await repo.insert(event)
    assert inserted.id is not None
    assert inserted.event_id is not None
    assert inserted.event_version == 2
    assert inserted.correlation_id == "corr-1"
    assert inserted.source_client == "web"


async def test_insert_resource_and_list(uow):
    """Resource links attach to event, list returns them in insertion order."""
    event = await _make_event(uow)
    res_a = await uow.audit_events.insert_resource(
        audit_event_id=event.id,
        resource_type="item",
        resource_id="101",
        relation="primary",
    )
    res_b = await uow.audit_events.insert_resource(
        audit_event_id=event.id,
        resource_type="operation",
        resource_id="op-uuid",
        relation="generated",
        snapshot_before={"a": 1},
        snapshot_after={"a": 2},
    )
    rows = await uow.audit_events.list_resources(event.id)
    assert [r.relation for r in rows] == ["primary", "generated"]
    assert res_b.snapshot_before == {"a": 1}
    assert res_b.snapshot_after == {"a": 2}


async def test_insert_effect_records_snapshot_fields(uow, db_session):
    """Insert effect with snapshot fields populated from inventory_subject/item."""
    # Use a fresh item so the test schema is self-contained.
    fresh_item, site_id = await _make_item(uow, "AUDIT-REPO-1", "Audit repo item")
    subject = await uow.inventory_subjects.get_or_create_for_item(item_id=fresh_item.id)
    event = await _make_event(uow)

    effect = AuditItemEffect(
        audit_event_id=event.id,
        operation_id=None,
        inventory_subject_id=subject.id,
        item_id=fresh_item.id,
        item_name_snapshot=fresh_item.name,
        item_sku_snapshot=fresh_item.sku,
        subject_type="catalog_item",
        site_id=site_id,
        quantity_before=0,
        quantity_delta=5,
        quantity_after=5,
        effect_type="adjustment",
        is_system_generated=False,
        caused_by_event_id=None,
        note="repo smoke",
    )
    inserted = await uow.audit_events.insert_effect(effect)
    assert inserted.id is not None
    assert inserted.item_name_snapshot == fresh_item.name
    assert inserted.effect_type == "adjustment"


async def test_list_by_correlation_id(uow):
    """Two events sharing a correlation id are returned together."""
    a = await _make_event(uow, event_type="a")
    b = await _make_event(uow, event_type="b")
    await uow.session.execute(
        AuditEvent.__table__.update().where(AuditEvent.id == a.id).values(correlation_id="corr-xyz")
    )
    await uow.session.execute(
        AuditEvent.__table__.update().where(AuditEvent.id == b.id).values(correlation_id="corr-xyz")
    )
    rows = await uow.audit_events.list_by_correlation_id("corr-xyz")
    assert {r.id for r in rows} == {a.id, b.id}


async def test_list_by_parent_event_id(uow):
    """Child events reference their parent via audit_events.parent_event_id."""
    parent = await _make_event(uow, event_type="item.merge")
    child = AuditEvent(
        event_type="operation.submit",
        event_version=2,
        actor_user_id=None,
        entity_type="operation",
        entity_id="op-1",
        summary="child",
        parent_event_id=parent.event_id,
    )
    inserted_child = await uow.audit_events.insert(child)
    children = await uow.audit_events.list_by_parent_event_id(parent.event_id)
    assert [c.id for c in children] == [inserted_child.id]


async def test_list_events_filter_by_outcome_and_correlation(uow, db_session):
    """list_events picks up outcome + correlation_id filters."""
    e1 = await _make_event(uow, event_type="e1")
    e2 = await _make_event(uow, event_type="e2")
    await db_session.execute(
        AuditEvent.__table__.update().where(AuditEvent.id == e1.id).values(correlation_id="x", outcome="success")
    )
    await db_session.execute(
        AuditEvent.__table__.update().where(AuditEvent.id == e2.id).values(correlation_id="x", outcome="partial")
    )
    await db_session.flush()
    # Expire any cached instances so we read the freshly-updated columns.
    db_session.expire_all()
    rows, total = await uow.audit_events.list_events(correlation_id="x", outcome="partial")
    assert total >= 1
    assert all(r.outcome == "partial" for r in rows)


async def test_get_effects_by_item_pagination(uow, db_session):
    """Insert several effects for one item, fetch page 1."""
    fresh_item, site_id = await _make_item(uow, "AUDIT-REPO-PAGE", "Audit repo page")
    subject = await uow.inventory_subjects.get_or_create_for_item(item_id=fresh_item.id)
    event = await _make_event(uow)
    for i in range(3):
        await uow.audit_events.insert_effect(
            AuditItemEffect(
                audit_event_id=event.id,
                operation_id=None,
                inventory_subject_id=subject.id,
                item_id=fresh_item.id,
                item_name_snapshot=fresh_item.name,
                item_sku_snapshot=fresh_item.sku,
                subject_type="catalog_item",
                site_id=site_id,
                quantity_before=0,
                quantity_delta=i + 1,
                quantity_after=i + 1,
                effect_type="adjustment",
                is_system_generated=False,
            )
        )
    await db_session.flush()
    rows, total = await uow.audit_events.get_effects_by_item(
        fresh_item.id, effect_type="adjustment", page=1, page_size=10,
    )
    assert total >= 3
    assert len(rows) >= 3


async def test_get_effects_by_subject_for_temporary_item(uow, db_session):
    """get_effects_by_subject works even when item_id is null (temporary item)."""
    fresh_item, site_id = await _make_item(uow, "AUDIT-REPO-TMP", "Audit repo tmp")
    subject = await uow.inventory_subjects.get_or_create_for_item(item_id=fresh_item.id)
    event = await _make_event(uow)
    await uow.audit_events.insert_effect(
        AuditItemEffect(
            audit_event_id=event.id,
            operation_id=None,
            inventory_subject_id=subject.id,
            item_id=None,  # represent a temporary-item effect
            item_name_snapshot="Tmp Item",
            item_sku_snapshot=None,
            subject_type="temporary_item",
            site_id=site_id,
            quantity_before=0,
            quantity_delta=1,
            quantity_after=1,
            effect_type="adjustment",
            is_system_generated=False,
        )
    )
    await db_session.flush()
    rows, total = await uow.audit_events.get_effects_by_subject(subject.id)
    assert total >= 1
    assert rows[0].item_id is None
    assert rows[0].subject_type == "temporary_item"


async def test_resource_fk_restrict_blocks_event_delete(uow, db_session):
    """RESTRICT on audit_event_resources.audit_event_id prevents deleting
    a parent event while resources reference it.
    """
    event = await _make_event(uow)
    await uow.audit_events.insert_resource(
        audit_event_id=event.id,
        resource_type="item",
        resource_id="1",
        relation="primary",
    )
    await db_session.flush()

    # Direct DB-level DELETE inside a savepoint must fail (FK RESTRICT).
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                text("DELETE FROM audit_events WHERE id = :id"),
                {"id": event.id},
            )
