"""Agent role (ADR-0030) — audit actor and catalog change payload tests.

Covers TZ-AGENT-ROLE-SYNCSERVER §10.7 / checklist item 7:
- when the agent creates catalog entities, created_by_user_id = agent UUID;
- when the agent PATCHes catalog entities through the allow-list, the change
  is recorded with updated_by_user_id = agent UUID (actor is the agent, never
  an impersonated chief token);
- the catalog change payload (old/new values) is written to audit_events.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.user import User
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
