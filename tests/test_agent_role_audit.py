"""Agent role (ADR-0030) — audit actor and catalog change payload tests.

Covers TZ-AGENT-ROLE-SYNCSERVER §10.7 / checklist item 7:
- when the agent creates catalog entities, created_by_user_id = agent UUID;
- when the agent PATCHes catalog entities through the allow-list, the change
  is recorded with updated_by_user_id = agent UUID (actor is the agent, never
  an impersonated chief token);
- the catalog change payload (old/new values) is written to audit_events;
- merge events carry actor_user_id == agent;
- draft operation create/PATCH carries actor_user_id == agent;
- chief_storekeeper never appears as actor for agent actions.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.models import Balance, Category, InventorySubject, Item, Operation, OperationLine, Site, Unit, User
from app.schemas.catalog import (
    CategoryCreateRequest,
    CategoryUpdateRequest,
    ItemCreateRequest,
    ItemUpdateRequest,
    UnitCreateRequest,
    UnitUpdateRequest,
)
from app.services.catalog_admin_service import CatalogAdminService


@pytest.fixture
async def agent_user(db_session) -> User:
    """Agent-role user (ADR-0030): draft/catalog authority, no admin."""
    agent_obj = User(
        username=f"agent-{uuid4().hex[:8]}",
        email=f"agent-{uuid4().hex[:8]}@example.com",
        full_name="Agent Test",
        is_active=True,
        is_root=False,
        role="agent",
        default_site_id=None,
    )
    db_session.add(agent_obj)
    await db_session.flush()
    return agent_obj


@pytest.fixture
async def chief_user(db_session) -> User:
    """Chief storekeeper for impersonation-negative tests."""
    chief_obj = User(
        username=f"chief-{uuid4().hex[:8]}",
        email=f"chief-{uuid4().hex[:8]}@example.com",
        full_name="Chief Test",
        is_active=True,
        is_root=False,
        role="chief_storekeeper",
        default_site_id=None,
    )
    db_session.add(chief_obj)
    await db_session.flush()
    return chief_obj


async def _create_unit(uow, name: str = "AA Unit", symbol: str = "AAU") -> Unit:
    return await CatalogAdminService().create_unit(
        uow, UnitCreateRequest(name=name, symbol=symbol),
    )


async def _create_category(uow, name: str = "AA Cat", code: str | None = None) -> Category:
    return await CatalogAdminService().create_category(
        uow, CategoryCreateRequest(name=name, code=code),
    )


async def _create_item(uow, *, unit: Unit, category: Category, name: str = "AA Item") -> Item:
    return await CatalogAdminService().create_item(
        uow, ItemCreateRequest(name=name, unit_id=unit.id, category_id=category.id),
    )


@pytest.mark.asyncio
async def test_agent_create_sets_actor_to_agent_id(uow, agent_user) -> None:
    """TZ §10.7: catalog create records the agent's own UUID as actor."""
    service = CatalogAdminService()

    unit = await service.create_unit(
        uow,
        UnitCreateRequest(name="Agent Audit Unit", symbol="AAU"),
        created_by_user_id=agent_user.id,
    )
    assert unit.created_by_user_id == agent_user.id

    category = await service.create_category(
        uow,
        CategoryCreateRequest(name="Agent Audit Category"),
        created_by_user_id=agent_user.id,
    )
    assert category.created_by_user_id == agent_user.id

    item = await service.create_item(
        uow,
        ItemCreateRequest(
            name="Agent Audit Item",
            sku="AAI-1",
            unit_id=unit.id,
            category_id=category.id,
            is_active=True,
        ),
        created_by_user_id=agent_user.id,
    )
    assert item.created_by_user_id == agent_user.id


@pytest.mark.asyncio
async def test_agent_patch_sets_actor_and_audit_changes(uow, agent_user, db_session) -> None:
    """TZ §10.7: agent PATCH writes updated_by_user_id = agent UUID and the
    old/new change payload into audit_events."""
    service = CatalogAdminService()

    item = await service.create_item(
        uow,
        ItemCreateRequest(
            name="Original Name",
            sku="AAI-2",
            unit_id=(await service.create_unit(uow, UnitCreateRequest(name="U", symbol="U2"))).id,
            is_active=True,
        ),
        created_by_user_id=agent_user.id,
    )

    updated = await service.update_item(
        uow,
        item.id,
        ItemUpdateRequest(name="Renamed By Agent", description="changed by agent"),
        updated_by_user_id=agent_user.id,
    )
    assert updated.updated_by_user_id == agent_user.id
    assert updated.name == "Renamed By Agent"
    assert updated.description == "changed by agent"

    # change payload (old/new) is recorded in audit_events with agent actor
    events, _ = await uow.audit_events.list_events(
        event_type="item.update",
        entity_type="item",
        entity_id=str(item.id),
    )
    assert events, "audit event expected for agent catalog PATCH"
    event = events[0]
    assert event.actor_user_id == agent_user.id
    assert event.changes is not None
    assert event.changes.get("name", {}).get("old") == "Original Name"
    assert event.changes.get("name", {}).get("new") == "Renamed By Agent"


@pytest.mark.asyncio
async def test_agent_patch_category_records_actor(uow, agent_user) -> None:
    """TZ §10.7: category PATCH by agent records the agent actor."""
    service = CatalogAdminService()
    category = await service.create_category(
        uow,
        CategoryCreateRequest(name="Agent Cat", code="AGCAT"),
        created_by_user_id=agent_user.id,
    )
    updated = await service.update_category(
        uow,
        category.id,
        CategoryUpdateRequest(sort_order=7),
        updated_by_user_id=agent_user.id,
    )
    assert updated.updated_by_user_id == agent_user.id
    assert updated.sort_order == 7


# ─── Merge audit actor (issue #21 gap #3) ─────────────────────────────


async def _merge_item_setup(uow, site, actor: User) -> tuple[Item, Item]:
    """Create source/target items with inventory subjects and balance."""
    unit = await _create_unit(uow, name="Merge Unit", symbol="MU")
    category = await _create_category(uow, name="Merge Cat")
    source = await _create_item(uow, unit=unit, category=category, name="Merge Source")
    target = await _create_item(uow, unit=unit, category=category, name="Merge Target")

    source_subject = InventorySubject(subject_type="catalog_item", item_id=source.id)
    uow.session.add(source_subject)
    await uow.session.flush()

    target_subject = InventorySubject(subject_type="catalog_item", item_id=target.id)
    uow.session.add(target_subject)
    await uow.session.flush()

    uow.session.add(
        Balance(
            site_id=site.id,
            inventory_subject_id=source_subject.id,
            item_id=source.id,
            qty=Decimal("5.000"),
        )
    )
    await uow.session.flush()

    op = Operation(
        site_id=site.id,
        operation_type="ADJUSTMENT",
        status="submitted",
        created_by_user_id=actor.id,
    )
    uow.session.add(op)
    await uow.session.flush()

    uow.session.add(
        OperationLine(
            operation_id=op.id,
            line_number=1,
            inventory_subject_id=source_subject.id,
            item_id=source.id,
            qty=Decimal("5.000"),
        )
    )
    await uow.session.flush()

    return source, target


@pytest.mark.asyncio
async def test_agent_merge_items_actor_is_agent(uow, agent_user, site) -> None:
    """TZ §10.7: item merge records agent as actor, never impersonates chief."""
    source, target = await _merge_item_setup(uow, site, agent_user)

    merged = await CatalogAdminService().merge_items(
        uow,
        source_item_id=source.id,
        target_item_id=target.id,
        comment="agent merge test",
        resolved_by_user_id=agent_user.id,
    )
    assert merged.id == target.id

    events, _ = await uow.audit_events.list_events(
        event_type="item.merge",
        entity_type="item",
        entity_id=str(target.id),
    )
    assert events, "item.merge audit event expected"
    assert events[0].actor_user_id == agent_user.id


@pytest.mark.asyncio
async def test_agent_merge_categories_actor_is_agent(uow, agent_user) -> None:
    """TZ §10.7: category merge records agent as actor."""
    source_cat = await _create_category(uow, name="Merge Src", code="MSRC")
    target_cat = await _create_category(uow, name="Merge Tgt", code="MTGT")

    merged = await CatalogAdminService().merge_categories(
        uow,
        source_category_id=source_cat.id,
        target_category_id=target_cat.id,
        comment="agent cat merge",
        resolved_by_user_id=agent_user.id,
    )
    assert merged.id == target_cat.id

    events, _ = await uow.audit_events.list_events(
        event_type="category.merge",
        entity_type="category",
        entity_id=str(target_cat.id),
    )
    assert events, "category.merge audit event expected"
    assert events[0].actor_user_id == agent_user.id


# ─── Draft operations audit actor (issue #21 gap #4) ──────────────────


@pytest.mark.asyncio
async def test_agent_draft_create_actor_is_agent(
    client: AsyncClient, uow, agent_user, site, db_session,
) -> None:
    """TZ §10.7: operation.create audit event carries the real agent user id
    as actor — not a tautological comparison."""
    unit = await _create_unit(uow, name="Draft Unit", symbol="DU")
    category = await _create_category(uow, name="Draft Cat", code="DCAT")
    item = await _create_item(uow, unit=unit, category=category, name="Draft Item")

    resp = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": str(agent_user.user_token)},
        json={
            "operation_type": "RECEIVE",
            "site_id": site.id,
            "lines": [{"line_number": 1, "item_id": item.id, "qty": 3}],
            "notes": "audit actor test",
        },
    )
    assert resp.status_code == 200, resp.text
    op_id = resp.json()["id"]

    # Query audit event directly — compare against the REAL agent UUID,
    # not against the tautological created_by_user_id from the response.
    events, _ = await uow.audit_events.list_events(
        event_type="operation.create",
        entity_type="operation",
        entity_id=str(op_id),
    )
    assert events, "operation.create audit event expected"
    assert events[0].actor_user_id == agent_user.id


@pytest.mark.asyncio
async def test_agent_draft_patch_actor_is_agent(
    client: AsyncClient, uow, agent_user, site, db_session,
) -> None:
    """TZ §10.7: operation.update audit event from PATCH carries agent actor."""
    unit = await _create_unit(uow, name="Patch Unit", symbol="PU")
    category = await _create_category(uow, name="Patch Cat", code="PCAT")
    item = await _create_item(uow, unit=unit, category=category, name="Patch Item")

    create_resp = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": str(agent_user.user_token)},
        json={
            "operation_type": "RECEIVE",
            "site_id": site.id,
            "lines": [{"line_number": 1, "item_id": item.id, "qty": 2}],
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    op_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/api/v1/operations/{op_id}",
        headers={"X-User-Token": str(agent_user.user_token)},
        json={"notes": "patched by agent for audit"},
    )
    assert patch_resp.status_code == 200, patch_resp.text

    events, _ = await uow.audit_events.list_events(
        event_type="operation.update",
        entity_type="operation",
        entity_id=str(op_id),
    )
    assert events, "operation.update audit event expected"
    assert events[0].actor_user_id == agent_user.id


# ─── Negative impersonation (issue #21 gap #6) ────────────────────────


@pytest.mark.asyncio
async def test_agent_actions_never_impersonate_chief_storekeeper(
    uow, agent_user, chief_user, site,
) -> None:
    """Negative: chief_storekeeper must never appear as actor for actions
    performed by the agent — catalog create, catalog PATCH, and merge."""
    unit = await _create_unit(uow, name="Imp Unit", symbol="IMPU")
    category = await _create_category(uow, name="Imp Cat", code="IMPC")
    item = await _create_item(uow, unit=unit, category=category, name="Imp Item")

    await CatalogAdminService().update_item(
        uow, item.id,
        ItemUpdateRequest(name="Imp Renamed"),
        updated_by_user_id=agent_user.id,
    )

    source, target = await _merge_item_setup(uow, site, agent_user)
    await CatalogAdminService().merge_items(
        uow,
        source_item_id=source.id,
        target_item_id=target.id,
        resolved_by_user_id=agent_user.id,
    )

    # Scan ALL audit events written during this test — chief must never appear
    all_events, _ = await uow.audit_events.list_events(page_size=200)
    for evt in all_events:
        assert evt.actor_user_id != chief_user.id, (
            f"chief_storekeeper leaked as actor in event {evt.event_type} "
            f"(id={evt.id}, actor={evt.actor_user_id})"
        )
