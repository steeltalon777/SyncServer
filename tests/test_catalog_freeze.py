from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.asset_register import LostAssetBalance
from app.models.category import Category
from app.models.inventory_subject import InventorySubject
from app.models.item import Item
from app.models.operation import Operation, OperationLine
from app.models.site import Site
from app.models.unit import Unit
from app.models.user import User
from app.models.user_access_scope import UserAccessScope
from app.schemas.catalog import ItemUpdateRequest
from app.services.catalog_admin_service import CatalogAdminService
from app.services.uow import UnitOfWork
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

    app.dependency_overrides.clear()
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

        chief = User(
            username=f"chief-{suffix}",
            email=f"chief-{suffix}@example.com",
            full_name="Chief",
            is_active=True,
            is_root=False,
            role="chief_storekeeper",
            default_site_id=site.id,
        )
        sender = User(
            username=f"sender-{suffix}",
            email=f"sender-{suffix}@example.com",
            full_name="Sender",
            is_active=True,
            is_root=False,
            role="storekeeper",
            default_site_id=site.id,
        )
        session.add_all([chief, sender])
        await session.flush()

        session.add(
            UserAccessScope(
                user_id=sender.id,
                site_id=site.id,
                can_view=True,
                can_operate=True,
                can_manage_catalog=False,
                is_active=True,
            )
        )

        unit = Unit(code=f"PC-{suffix}", name=f"Piece {suffix}", symbol=f"pc{suffix[:3]}", is_active=True)
        session.add(unit)
        await session.flush()

        category = Category(
            code=f"CAT-{suffix}",
            name=f"Category {suffix}",
            normalized_name=f"category {suffix}",
            is_active=True,
        )
        session.add(category)
        await session.flush()

        item = Item(
            sku=f"SKU-{suffix}",
            name=f"Item {suffix}",
            normalized_name=f"item {suffix}",
            category_id=category.id,
            unit_id=unit.id,
            is_active=True,
        )
        session.add(item)
        await session.commit()

        return {
            "site_id": site.id,
            "item_id": item.id,
            "unit": unit,
            "category": category,
            "chief_user_id": chief.id,
            "sender_user_id": sender.id,
            "chief_token": str(chief.user_token),
            "sender_token": str(sender.user_token),
        }


# ─── Level 1: Repo-level unit tests ────────────────────────────────────────

@pytest.mark.asyncio
async def test_repo_no_inventory_subject_not_frozen(session_factory):
    """Item with no inventory subject is not frozen."""
    seed = await _seed_fixture(session_factory)
    async with session_factory() as session:
        uow = UnitOfWork(session)
        frozen = await uow.asset_registers.has_active_lost_for_item(seed["item_id"])
        assert frozen is False
        await session.rollback()


@pytest.mark.asyncio
async def test_repo_no_lost_row_not_frozen(session_factory):
    """Item with inventory subject and no lost row is not frozen."""
    seed = await _seed_fixture(session_factory)
    async with session_factory() as session:
        inv_subject = InventorySubject(subject_type="catalog_item", item_id=seed["item_id"])
        session.add(inv_subject)
        await session.flush()

        uow = UnitOfWork(session)
        frozen = await uow.asset_registers.has_active_lost_for_item(seed["item_id"])
        assert frozen is False
        await session.rollback()


async def _create_operation_line(session, item_id, site_id, user_id):
    """Create a minimal operation + line and return (op_id, line_id)."""
    op = Operation(
        site_id=site_id,
        operation_type="RECEIVE",
        status="draft",
        created_by_user_id=user_id,
        effective_at=datetime.now(UTC),
    )
    session.add(op)
    await session.flush()

    line = OperationLine(
        operation_id=op.id,
        line_number=1,
        qty=Decimal("10"),
        item_id=item_id,
    )
    session.add(line)
    await session.flush()
    return op.id, line.id


@pytest.mark.asyncio
async def test_repo_lost_qty_zero_not_frozen(session_factory):
    """Lost row with qty == 0 is not frozen."""
    seed = await _seed_fixture(session_factory)
    async with session_factory() as session:
        inv_subject = InventorySubject(subject_type="catalog_item", item_id=seed["item_id"])
        session.add(inv_subject)
        await session.flush()

        op_id, line_id = await _create_operation_line(session, seed["item_id"], seed["site_id"], seed["sender_user_id"])

        lost = LostAssetBalance(
            operation_line_id=line_id,
            operation_id=op_id,
            site_id=seed["site_id"],
            inventory_subject_id=inv_subject.id,
            qty=Decimal("0"),
        )
        session.add(lost)
        await session.flush()

        uow = UnitOfWork(session)
        frozen = await uow.asset_registers.has_active_lost_for_item(seed["item_id"])
        assert frozen is False
        await session.rollback()


@pytest.mark.asyncio
async def test_repo_lost_qty_positive_is_frozen(session_factory):
    """Lost row with qty > 0 is frozen."""
    seed = await _seed_fixture(session_factory)
    async with session_factory() as session:
        inv_subject = InventorySubject(subject_type="catalog_item", item_id=seed["item_id"])
        session.add(inv_subject)
        await session.flush()

        op_id, line_id = await _create_operation_line(session, seed["item_id"], seed["site_id"], seed["sender_user_id"])

        lost = LostAssetBalance(
            operation_line_id=line_id,
            operation_id=op_id,
            site_id=seed["site_id"],
            inventory_subject_id=inv_subject.id,
            qty=Decimal("5"),
        )
        session.add(lost)
        await session.flush()

        uow = UnitOfWork(session)
        frozen = await uow.asset_registers.has_active_lost_for_item(seed["item_id"])
        assert frozen is True
        await session.rollback()


# ─── Level 2: Service-level freeze enforcement ───────────────────────────

@pytest.mark.asyncio
async def test_update_frozen_item_returns_409(session_factory):
    """Updating a frozen item returns 409 conflict."""
    seed = await _seed_fixture(session_factory)
    async with session_factory() as session:
        inv_subject = InventorySubject(subject_type="catalog_item", item_id=seed["item_id"])
        session.add(inv_subject)
        await session.flush()

        op_id, line_id = await _create_operation_line(session, seed["item_id"], seed["site_id"], seed["sender_user_id"])

        lost = LostAssetBalance(
            operation_line_id=line_id,
            operation_id=op_id,
            site_id=seed["site_id"],
            inventory_subject_id=inv_subject.id,
            qty=Decimal("3"),
        )
        session.add(lost)
        await session.flush()

        uow = UnitOfWork(session)
        service = CatalogAdminService()
        with pytest.raises(Exception) as exc:
            await service.update_item(uow, seed["item_id"], ItemUpdateRequest(name="New Name"))
        assert "frozen" in str(exc.value).lower()
        await session.rollback()


@pytest.mark.asyncio
async def test_delete_frozen_item_returns_409(session_factory):
    """Deleting a frozen item returns 409 conflict."""
    seed = await _seed_fixture(session_factory)
    async with session_factory() as session:
        inv_subject = InventorySubject(subject_type="catalog_item", item_id=seed["item_id"])
        session.add(inv_subject)
        await session.flush()

        op_id, line_id = await _create_operation_line(session, seed["item_id"], seed["site_id"], seed["sender_user_id"])

        lost = LostAssetBalance(
            operation_line_id=line_id,
            operation_id=op_id,
            site_id=seed["site_id"],
            inventory_subject_id=inv_subject.id,
            qty=Decimal("3"),
        )
        session.add(lost)
        await session.flush()

        uow = UnitOfWork(session)
        service = CatalogAdminService()
        with pytest.raises(Exception) as exc:
            await service.delete_item(uow, seed["item_id"], uuid4())
        assert "frozen" in str(exc.value).lower()
        await session.rollback()


@pytest.mark.asyncio
async def test_update_unfrozen_item_ok(session_factory):
    """Updating an unfrozen item works normally."""
    seed = await _seed_fixture(session_factory)
    async with session_factory() as session:
        uow = UnitOfWork(session)
        service = CatalogAdminService()
        result = await service.update_item(uow, seed["item_id"], ItemUpdateRequest(name="Updated Name"))
        assert result.name == "Updated Name"
        await session.rollback()


# ─── Level 3: Full integration — freeze → resolve → unfreeze ───────────────

@pytest.mark.asyncio
async def test_full_flow_lost_resolve_unfreeze(client, session_factory):
    """
    Create a lost asset for a permanent item → verify freeze →
    resolve it → verify item update is allowed again.
    """
    seed = await _seed_fixture(session_factory)

    # 1. Create a RECEIVE operation and accept with losses
    resp = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["sender_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 10}],
        },
    )
    assert resp.status_code == 200
    op_id = resp.json()["id"]
    line_id = resp.json()["lines"][0]["id"]

    resp = await client.post(
        f"/api/v1/operations/{op_id}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert resp.status_code == 200

    resp = await client.post(
        f"/api/v1/operations/{op_id}/accept-lines",
        headers={"X-User-Token": seed["sender_token"]},
        json={"lines": [{"line_id": line_id, "accepted_qty": 7, "lost_qty": 3}]},
    )
    assert resp.status_code == 200

    # 2. Verify item is now frozen — both update and delete should fail
    resp = await client.patch(
        f"/api/v1/catalog/admin/items/{seed['item_id']}",
        headers={"X-User-Token": seed["chief_token"]},
        json={"name": "Hacked Name"},
    )
    assert resp.status_code == 409
    data = resp.json()
    assert "frozen" in data.get("detail", "").lower()

    resp = await client.delete(
        f"/api/v1/catalog/admin/items/{seed['item_id']}",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert resp.status_code == 409
    data = resp.json()
    assert "frozen" in data.get("detail", "").lower()

    # 3. Resolve the lost asset — write-off the lost qty
    lost_list = await client.get(
        "/api/v1/lost-assets",
        headers={"X-User-Token": seed["sender_token"]},
    )
    assert lost_list.status_code == 200
    assert lost_list.json()["total_count"] == 1
    lost_line_id = lost_list.json()["items"][0]["operation_line_id"]

    resp = await client.post(
        f"/api/v1/lost-assets/{lost_line_id}/resolve",
        headers={"X-User-Token": seed["chief_token"]},
        json={"action": "write_off", "qty": 3},
    )
    assert resp.status_code == 200

    # 4. Verify item is now editable again
    resp = await client.patch(
        f"/api/v1/catalog/admin/items/{seed['item_id']}",
        headers={"X-User-Token": seed["chief_token"]},
        json={"name": "New Name After Resolve"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name After Resolve"
