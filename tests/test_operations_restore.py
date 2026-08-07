from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.audit_event import AuditEvent
from app.models.category import Category
from app.models.item import Item
from app.models.site import Site
from app.models.unit import Unit
from app.models.user import User
from app.models.user_access_scope import UserAccessScope
from main import create_app

app = create_app(enable_startup_migrations=False)


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

        root_user = User(
            username=f"root-{suffix}",
            email=f"root-{suffix}@example.com",
            full_name="Root",
            is_active=True,
            is_root=True,
            role="root",
            default_site_id=site.id,
        )
        storekeeper = User(
            username=f"storekeeper-{suffix}",
            email=f"storekeeper-{suffix}@example.com",
            full_name="Storekeeper",
            is_active=True,
            is_root=False,
            role="storekeeper",
            default_site_id=site.id,
        )
        session.add_all([root_user, storekeeper])
        await session.flush()

        session.add_all([
            UserAccessScope(
                user_id=storekeeper.id, site_id=site.id,
                can_view=True, can_operate=True, can_manage_catalog=False, is_active=True,
            ),
        ])

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
        await session.flush()

        await session.commit()

        return {
            "site_id": site.id,
            "item_id": item.id,
            "root_token": str(root_user.user_token),
            "storekeeper_token": str(storekeeper.user_token),
        }


async def _create_receive_op(client, token, site_id, item_id, qty=10):
    """Create a RECEIVE draft. Returns operation dict."""
    r = await client.post("/api/v1/operations", headers={"X-User-Token": token}, json={
        "operation_type": "RECEIVE", "site_id": site_id,
        "lines": [{"line_number": 1, "item_id": item_id, "qty": qty}],
    })
    assert r.status_code == 200, r.text
    return r.json()


async def _submit_op(client, token, op_id):
    r = await client.post(f"/api/v1/operations/{op_id}/submit", headers={"X-User-Token": token},
                          json={"submit": True})
    assert r.status_code == 200, r.text
    return r.json()


async def _cancel_op(client, token, op_id):
    r = await client.post(f"/api/v1/operations/{op_id}/cancel", headers={"X-User-Token": token},
                          json={"cancel": True, "reason": "test cancel"})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# AC-1A.1: Root restores cancelled operation → 200, status → draft
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_restore_cancelled_operation_by_root_succeeds(client, session_factory):
    seed = await _seed_fixture(session_factory)
    op = await _create_receive_op(client, seed["root_token"], seed["site_id"], seed["item_id"])
    await _submit_op(client, seed["root_token"], op["id"])
    await _cancel_op(client, seed["root_token"], op["id"])

    r = await client.post(f"/api/v1/operations/{op['id']}/restore",
                          headers={"X-User-Token": seed["root_token"]},
                          json={"restore": True})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "draft"
    assert data["id"] == str(op["id"])


# ---------------------------------------------------------------------------
# AC-1A.2: Storekeeper (non-root) → 403
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_restore_by_storekeeper_fails(client, session_factory):
    seed = await _seed_fixture(session_factory)
    op = await _create_receive_op(client, seed["root_token"], seed["site_id"], seed["item_id"])
    await _submit_op(client, seed["root_token"], op["id"])
    await _cancel_op(client, seed["root_token"], op["id"])

    r = await client.post(f"/api/v1/operations/{op['id']}/restore",
                          headers={"X-User-Token": seed["storekeeper_token"]},
                          json={"restore": True})
    assert r.status_code == 403, r.text
    assert "only root can restore cancelled operations" in r.text


# ---------------------------------------------------------------------------
# AC-1A.3: Restore non-cancelled operation → 409
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_restore_draft_operation_fails(client, session_factory):
    seed = await _seed_fixture(session_factory)
    op = await _create_receive_op(client, seed["root_token"], seed["site_id"], seed["item_id"])

    r = await client.post(f"/api/v1/operations/{op['id']}/restore",
                          headers={"X-User-Token": seed["root_token"]},
                          json={"restore": True})
    assert r.status_code == 409, r.text
    assert "only cancelled operations can be restored" in r.text


@pytest.mark.asyncio
async def test_restore_submitted_operation_fails(client, session_factory):
    seed = await _seed_fixture(session_factory)
    op = await _create_receive_op(client, seed["root_token"], seed["site_id"], seed["item_id"])
    await _submit_op(client, seed["root_token"], op["id"])

    r = await client.post(f"/api/v1/operations/{op['id']}/restore",
                          headers={"X-User-Token": seed["root_token"]},
                          json={"restore": True})
    assert r.status_code == 409, r.text
    assert "only cancelled operations can be restored" in r.text


# ---------------------------------------------------------------------------
# AC-1A.4: Restore non-existent operation → 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_restore_nonexistent_operation_fails(client, session_factory):
    seed = await _seed_fixture(session_factory)
    fake_id = uuid4()

    r = await client.post(f"/api/v1/operations/{fake_id}/restore",
                          headers={"X-User-Token": seed["root_token"]},
                          json={"restore": True})
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# AC-1A.5: After restore, PATCH and submit work as for draft
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_restored_operation_supports_patch_and_submit(client, session_factory):
    seed = await _seed_fixture(session_factory)
    op = await _create_receive_op(client, seed["root_token"], seed["site_id"], seed["item_id"])
    await _submit_op(client, seed["root_token"], op["id"])
    await _cancel_op(client, seed["root_token"], op["id"])

    r = await client.post(f"/api/v1/operations/{op['id']}/restore",
                          headers={"X-User-Token": seed["root_token"]},
                          json={"restore": True})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "draft"

    r2 = await client.patch(f"/api/v1/operations/{op['id']}",
                            headers={"X-User-Token": seed["root_token"]},
                            json={"notes": "restored and updated"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["notes"] == "restored and updated"

    r3 = await client.post(f"/api/v1/operations/{op['id']}/submit",
                           headers={"X-User-Token": seed["root_token"]},
                           json={"submit": True})
    assert r3.status_code == 200, r3.text
    assert r3.json()["status"] == "submitted"


# ---------------------------------------------------------------------------
# ADR-0028 A-2: restore writes operation.restore audit event
# ---------------------------------------------------------------------------


async def _find_restore_event(session_factory, operation_id):
    async with session_factory() as session:
        result = await session.execute(
            select(AuditEvent).where(
                AuditEvent.event_type == "operation.restore",
                AuditEvent.entity_id == str(operation_id),
            )
        )
        return result.scalar_one_or_none()


@pytest.mark.asyncio
async def test_restore_writes_audit_event_with_parent_cancel(client, session_factory):
    """A-2: successful restore writes operation.restore with correct changes
    and parent_event_id pointing at the last successful operation.cancel event.
    """
    seed = await _seed_fixture(session_factory)
    op = await _create_receive_op(client, seed["root_token"], seed["site_id"], seed["item_id"])
    await _submit_op(client, seed["root_token"], op["id"])
    await _cancel_op(client, seed["root_token"], op["id"])

    r = await client.post(f"/api/v1/operations/{op['id']}/restore",
                          headers={"X-User-Token": seed["root_token"]},
                          json={"restore": True})
    assert r.status_code == 200, r.text

    restore_event = await _find_restore_event(session_factory, op["id"])
    assert restore_event is not None
    assert restore_event.outcome == "success"
    changes = dict(restore_event.changes or {})
    assert changes["previous_status"] == "cancelled"
    assert changes["new_status"] == "draft"
    assert changes["previous_version"] < changes["new_version"]
    assert changes["restored_by_user_id"] is not None
    assert "cancelled_at_before" in changes
    assert "cancelled_by_user_id_before" in changes
    # cancel_event happens through the same root user right before restore
    assert restore_event.parent_event_id is not None


@pytest.mark.asyncio
async def test_restore_writes_cancel_event_missing_when_legacy(client, session_factory):
    """A-2: when no cancel audit event is found the audit row records
    cancel_event_missing=True and parent_event_id stays None.
    """
    seed = await _seed_fixture(session_factory)
    op = await _create_receive_op(client, seed["root_token"], seed["site_id"], seed["item_id"])
    await _submit_op(client, seed["root_token"], op["id"])
    await _cancel_op(client, seed["root_token"], op["id"])

    # Wipe the audit history for this operation to simulate a legacy gap.
    async with session_factory() as session:
        await session.execute(
            AuditEvent.__table__.delete().where(
                AuditEvent.entity_id == str(op["id"]),
                AuditEvent.event_type.in_(("operation.cancel",)),
            )
        )
        await session.commit()

    r = await client.post(f"/api/v1/operations/{op['id']}/restore",
                          headers={"X-User-Token": seed["root_token"]},
                          json={"restore": True})
    assert r.status_code == 200, r.text

    restore_event = await _find_restore_event(session_factory, op["id"])
    assert restore_event is not None
    assert restore_event.parent_event_id is None
    changes = dict(restore_event.changes or {})
    assert changes.get("cancel_event_missing") is True


@pytest.mark.asyncio
async def test_failed_restore_writes_no_event(client, session_factory):
    """A-2: failed restore (403 storekeeper / 409 wrong state) does not
    write an operation.restore audit event.
    """
    seed = await _seed_fixture(session_factory)
    op = await _create_receive_op(client, seed["root_token"], seed["site_id"], seed["item_id"])
    await _submit_op(client, seed["root_token"], op["id"])
    await _cancel_op(client, seed["root_token"], op["id"])

    # storekeeper is not root
    r = await client.post(f"/api/v1/operations/{op['id']}/restore",
                          headers={"X-User-Token": seed["storekeeper_token"]},
                          json={"restore": True})
    assert r.status_code == 403, r.text

    restore_event = await _find_restore_event(session_factory, op["id"])
    assert restore_event is None, "storekeeper 403 must not write audit event"

    # root tries to restore a draft (409 from workflow)
    draft_op = await _create_receive_op(client, seed["root_token"], seed["site_id"], seed["item_id"])
    r2 = await client.post(f"/api/v1/operations/{draft_op['id']}/restore",
                           headers={"X-User-Token": seed["root_token"]},
                           json={"restore": True})
    assert r2.status_code == 409, r2.text
    draft_event = await _find_restore_event(session_factory, draft_op["id"])
    assert draft_event is None


@pytest.mark.asyncio
async def test_repeated_restore_does_not_create_duplicate_event(client, session_factory):
    """A-2: a second restore against an already-restored draft is rejected
    by the workflow guard and produces no additional audit row.
    """
    seed = await _seed_fixture(session_factory)
    op = await _create_receive_op(client, seed["root_token"], seed["site_id"], seed["item_id"])
    await _submit_op(client, seed["root_token"], op["id"])
    await _cancel_op(client, seed["root_token"], op["id"])

    r = await client.post(f"/api/v1/operations/{op['id']}/restore",
                          headers={"X-User-Token": seed["root_token"]},
                          json={"restore": True})
    assert r.status_code == 200, r.text

    # second attempt → 409 (status is now 'draft')
    r2 = await client.post(f"/api/v1/operations/{op['id']}/restore",
                           headers={"X-User-Token": seed["root_token"]},
                           json={"restore": True})
    assert r2.status_code == 409, r2.text

    # exactly one restore event
    async with session_factory() as session:
        rows = (await session.execute(
            select(AuditEvent.event_id).where(
                AuditEvent.event_type == "operation.restore",
                AuditEvent.entity_id == str(op["id"]),
            )
        )).scalars().all()
    assert len(list(rows)) == 1
