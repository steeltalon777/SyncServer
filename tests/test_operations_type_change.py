from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.category import Category
from app.models.item import Item
from app.models.site import Site
from app.models.unit import Unit
from app.models.user import User
from app.models.user_access_scope import UserAccessScope
from main import create_app

app = create_app(enable_startup_migrations=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def client(session_factory: async_sessionmaker[AsyncSession]):
    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.rollback()

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


async def _seed_fixture(session_factory: async_sessionmaker[AsyncSession]) -> dict:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"SITE-{suffix}", name=f"Site {suffix}")
        session.add(site)
        await session.flush()

        sender = User(
            username=f"sender-{suffix}",
            email=f"sender-{suffix}@example.com",
            full_name="Sender",
            is_active=True,
            is_root=False,
            role="storekeeper",
            default_site_id=site.id,
        )
        session.add(sender)
        await session.flush()

        session.add(
            UserAccessScope(
                user_id=sender.id, site_id=site.id,
                can_view=True, can_operate=True, can_manage_catalog=False, is_active=True,
            ),
        )

        unit = Unit(code=f"PC-{suffix}", name=f"Piece {suffix}", symbol=f"pc{suffix[:3]}", is_active=True)
        session.add(unit)
        await session.flush()

        category = Category(
            code=f"CAT-{suffix}", name=f"Category {suffix}",
            normalized_name=f"category {suffix}", is_active=True,
        )
        session.add(category)
        await session.flush()

        item = Item(
            sku=f"SKU-{suffix}", name=f"Item {suffix}",
            normalized_name=f"item {suffix}",
            category_id=category.id, unit_id=unit.id,
            is_active=True,
        )
        session.add(item)
        await session.commit()

        return {
            "site_id": site.id,
            "item_id": item.id,
            "unit_id": unit.id,
            "sender_token": str(sender.user_token),
        }


# ---------------------------------------------------------------------------
# Operation type change tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_change_type_from_receive_to_expense_succeeds(client, session_factory):
    """AC-1B.1: PATCH draft operation_type from RECEIVE to EXPENSE → 200, type changes."""
    seed = await _seed_fixture(session_factory)
    r = await client.post("/api/v1/operations", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "RECEIVE", "site_id": seed["site_id"],
        "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 5}],
    })
    assert r.status_code == 200, r.text
    op_id = r.json()["id"]
    assert r.json()["operation_type"] == "RECEIVE"

    r2 = await client.patch(f"/api/v1/operations/{op_id}", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "EXPENSE",
    })
    assert r2.status_code == 200, r2.text
    assert r2.json()["operation_type"] == "EXPENSE"


@pytest.mark.asyncio
async def test_change_type_to_issue_without_issue_object_rejected(client, session_factory):
    """AC-1B.2: PATCH operation_type to ISSUE without issue_object_id → 422."""
    seed = await _seed_fixture(session_factory)
    r = await client.post("/api/v1/operations", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "RECEIVE", "site_id": seed["site_id"],
        "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 5}],
    })
    assert r.status_code == 200, r.text
    op_id = r.json()["id"]

    r2 = await client.patch(f"/api/v1/operations/{op_id}", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "ISSUE",
    })
    assert r2.status_code == 422, r2.text
    assert "cannot change type to ISSUE without an issue object" in r2.text


@pytest.mark.asyncio
async def test_change_type_to_receive_with_temporary_item_succeeds(client, session_factory):
    """AC-1B.3: PATCH operation_type to RECEIVE with temporary items in lines → 200."""
    seed = await _seed_fixture(session_factory)
    r = await client.post("/api/v1/operations", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "EXPENSE", "site_id": seed["site_id"],
        "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 5}],
    })
    assert r.status_code == 200, r.text
    op_id = r.json()["id"]

    r2 = await client.patch(f"/api/v1/operations/{op_id}", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "RECEIVE",
        "lines": [{
            "line_number": 1,
            "temporary_item": {"client_key": "temp-key", "name": "Temp Item", "unit_id": seed["unit_id"]},
            "qty": 3,
        }],
    })
    assert r2.status_code == 200, r2.text
    assert r2.json()["operation_type"] == "RECEIVE"


@pytest.mark.asyncio
async def test_change_type_to_non_receive_with_temporary_item_rejected(client, session_factory):
    """AC-1B.4: PATCH operation_type to EXPENSE with temporary items in lines → 422."""
    seed = await _seed_fixture(session_factory)
    r = await client.post("/api/v1/operations", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "RECEIVE", "site_id": seed["site_id"],
        "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 5}],
    })
    assert r.status_code == 200, r.text
    op_id = r.json()["id"]

    r2 = await client.patch(f"/api/v1/operations/{op_id}", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "EXPENSE",
        "lines": [{
            "line_number": 1,
            "temporary_item": {"client_key": "temp-key", "name": "Temp Item", "unit_id": seed["unit_id"]},
            "qty": 3,
        }],
    })
    assert r2.status_code == 422, r2.text
    assert "temporary items are only allowed for RECEIVE operations" in r2.text


@pytest.mark.asyncio
async def test_change_type_on_submitted_operation_rejected(client, session_factory):
    """AC-1B.5: PATCH submitted operation with new operation_type → 409."""
    seed = await _seed_fixture(session_factory)
    r = await client.post("/api/v1/operations", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "RECEIVE", "site_id": seed["site_id"],
        "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 5}],
    })
    assert r.status_code == 200, r.text
    op_id = r.json()["id"]

    submit = await client.post(f"/api/v1/operations/{op_id}/submit", headers={"X-User-Token": seed["sender_token"]},
                               json={"submit": True})
    assert submit.status_code == 200, submit.text

    r2 = await client.patch(f"/api/v1/operations/{op_id}", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "EXPENSE",
    })
    assert r2.status_code == 409, r2.text


@pytest.mark.asyncio
async def test_patch_without_operation_type_does_not_change_type(client, session_factory):
    """AC-1B.6: PATCH without operation_type → 200, type unchanged."""
    seed = await _seed_fixture(session_factory)
    r = await client.post("/api/v1/operations", headers={"X-User-Token": seed["sender_token"]}, json={
        "operation_type": "RECEIVE", "site_id": seed["site_id"],
        "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 5}],
    })
    assert r.status_code == 200, r.text
    op_id = r.json()["id"]
    assert r.json()["operation_type"] == "RECEIVE"

    r2 = await client.patch(f"/api/v1/operations/{op_id}", headers={"X-User-Token": seed["sender_token"]}, json={
        "notes": "test note without type change",
    })
    assert r2.status_code == 200, r2.text
    assert r2.json()["operation_type"] == "RECEIVE"
