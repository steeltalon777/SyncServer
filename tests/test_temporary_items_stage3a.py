from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.balance import Balance
from app.models.category import Category
from app.models.inventory_subject import InventorySubject
from app.models.item import Item
from app.models.operation import Operation, OperationLine
from app.models.site import Site
from app.models.temporary_item import TemporaryItem
from app.models.unit import Unit
from app.models.user import User
from app.models.user_access_scope import UserAccessScope
from main import create_app

app = create_app()


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


async def _seed(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"ST-{suffix}", name=f"Site {suffix}")
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
        storekeeper = User(
            username=f"storekeeper-{suffix}",
            email=f"storekeeper-{suffix}@example.com",
            full_name="Storekeeper",
            is_active=True,
            is_root=False,
            role="storekeeper",
            default_site_id=site.id,
        )
        session.add_all([chief, storekeeper])
        await session.flush()

        session.add_all(
            [
                UserAccessScope(
                    user_id=chief.id,
                    site_id=site.id,
                    can_view=True,
                    can_operate=True,
                    can_manage_catalog=True,
                    is_active=True,
                ),
                UserAccessScope(
                    user_id=storekeeper.id,
                    site_id=site.id,
                    can_view=True,
                    can_operate=True,
                    can_manage_catalog=False,
                    is_active=True,
                ),
            ]
        )

        unit = Unit(code=f"U-{suffix}", name=f"Unit {suffix}", symbol=f"u{suffix[:2]}", is_active=True)
        category = Category(code=f"C-{suffix}", name=f"Category {suffix}", normalized_name=f"category {suffix}", is_active=True)
        session.add_all([unit, category])
        await session.flush()

        catalog_item = Item(
            sku=f"SKU-{suffix}",
            name=f"Catalog Item {suffix}",
            normalized_name=f"catalog item {suffix}",
            category_id=category.id,
            unit_id=unit.id,
            is_active=True,
        )
        session.add(catalog_item)
        await session.commit()
        return {
            "site_id": site.id,
            "chief_token": str(chief.user_token),
            "storekeeper_token": str(storekeeper.user_token),
            "category_id": category.id,
            "unit_id": unit.id,
            "catalog_item_id": catalog_item.id,
        }


async def _create_temporary_item_with_balance(
    client: AsyncClient,
    seed: dict,
    client_request_id: str,
    client_key: str,
    qty: int = 5,
) -> dict:
    """Helper: create a RECEIVE operation with a temporary item, submit and accept it."""
    create_resp = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": client_request_id,
            "lines": [
                {
                    "line_number": 1,
                    "qty": qty,
                    "temporary_item": {
                        "client_key": client_key,
                        "name": f"Temp Item {client_key}",
                        "sku": None,
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                },
            ],
        },
    )
    assert create_resp.status_code == 200
    op = create_resp.json()
    temp_item_id = op["lines"][0]["temporary_item_id"]
    assert temp_item_id is not None

    # Submit
    submit_resp = await client.post(
        f"/api/v1/operations/{op['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_resp.status_code == 200

    # Accept lines (RECEIVE with acceptance_required)
    accept_resp = await client.post(
        f"/api/v1/operations/{op['id']}/accept-lines",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "lines": [
                {"line_id": op["lines"][0]["id"], "accepted_qty": qty, "lost_qty": 0},
            ]
        },
    )
    assert accept_resp.status_code == 200

    return {"temporary_item_id": temp_item_id, "operation_id": op["id"]}


# ============================================================
# Stage 3A: Approve as item
# ============================================================


@pytest.mark.asyncio
async def test_stage3a_approve_as_item_creates_new_item_and_transfers_balance(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Approve creates a new permanent item and transfers balance via service operations."""
    seed = await _seed(session_factory)
    result = await _create_temporary_item_with_balance(
        client, seed, "s3a-approve-1", "tmp-approve-1", qty=5,
    )
    temp_item_id = result["temporary_item_id"]

    # Approve
    approve_resp = await client.post(
        f"/api/v1/temporary-items/{temp_item_id}/approve-as-item",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert approve_resp.status_code == 200
    body = approve_resp.json()
    assert body["status"] == "approved_as_item"
    assert body["resolved_item_id"] is not None
    assert body["resolution_type"] == "approve_as_item"

    resolved_item_id = body["resolved_item_id"]

    async with session_factory() as session:
        # Verify new permanent item exists and is active
        new_item = await session.get(Item, resolved_item_id)
        assert new_item is not None
        assert new_item.is_active is True
        assert new_item.source_system == "temporary_item_resolution"

        # Verify new inventory subject exists for the new item
        new_subject = await session.execute(
            select(InventorySubject).where(InventorySubject.item_id == resolved_item_id)
        )
        new_subject = new_subject.scalar_one_or_none()
        assert new_subject is not None
        assert new_subject.subject_type == "catalog_item"

        # Verify balance was transferred to the new subject
        balance = await session.execute(
            select(Balance).where(
                Balance.site_id == seed["site_id"],
                Balance.inventory_subject_id == new_subject.id,
            )
        )
        balance = balance.scalar_one_or_none()
        assert balance is not None
        assert Decimal(str(balance.qty)) == Decimal("5")

        # Verify service operations were created
        service_ops = await session.execute(
            select(Operation).where(Operation.notes.ilike("%[resolution]%"))
        )
        service_ops = list(service_ops.scalars().all())
        # Should have at least 2 service operations (write-off + receipt)
        assert len(service_ops) >= 2


@pytest.mark.asyncio
async def test_stage3a_approve_as_item_blocks_when_pending_register_exists(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Approve must be blocked if temporary item has active pending registers."""
    seed = await _seed(session_factory)

    # Create a RECEIVE with acceptance_required (creates pending register)
    create_resp = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "s3a-block-pending-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 3,
                    "temporary_item": {
                        "client_key": "tmp-block-pending",
                        "name": "Block Pending Test",
                        "sku": None,
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                },
            ],
        },
    )
    assert create_resp.status_code == 200
    op = create_resp.json()
    temp_item_id = op["lines"][0]["temporary_item_id"]

    # Submit (creates pending register since acceptance_required)
    submit_resp = await client.post(
        f"/api/v1/operations/{op['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_resp.status_code == 200

    # Try to approve - should be blocked
    approve_resp = await client.post(
        f"/api/v1/temporary-items/{temp_item_id}/approve-as-item",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert approve_resp.status_code == 409
    assert "active" in approve_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_stage3a_approve_as_item_blocks_when_lost_register_exists(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Approve must be blocked if temporary item has active lost registers."""
    seed = await _seed(session_factory)

    # Create RECEIVE, submit, accept with partial loss
    create_resp = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "s3a-block-lost-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 5,
                    "temporary_item": {
                        "client_key": "tmp-block-lost",
                        "name": "Block Lost Test",
                        "sku": None,
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                },
            ],
        },
    )
    assert create_resp.status_code == 200
    op = create_resp.json()
    temp_item_id = op["lines"][0]["temporary_item_id"]

    # Submit
    submit_resp = await client.post(
        f"/api/v1/operations/{op['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_resp.status_code == 200

    # Accept with 2 lost, 3 accepted -> creates lost register with qty=2
    accept_resp = await client.post(
        f"/api/v1/operations/{op['id']}/accept-lines",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "lines": [
                {"line_id": op["lines"][0]["id"], "accepted_qty": 3, "lost_qty": 2},
            ]
        },
    )
    assert accept_resp.status_code == 200

    # Try to approve - should be blocked
    approve_resp = await client.post(
        f"/api/v1/temporary-items/{temp_item_id}/approve-as-item",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert approve_resp.status_code == 409
    assert "active" in approve_resp.json()["detail"].lower()


# ============================================================
# Stage 3A: Merge to existing item
# ============================================================


@pytest.mark.asyncio
async def test_stage3a_merge_to_item_transfers_balance(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Merge transfers balance from temporary item to target catalog item."""
    seed = await _seed(session_factory)
    result = await _create_temporary_item_with_balance(
        client, seed, "s3a-merge-1", "tmp-merge-1", qty=3,
    )
    temp_item_id = result["temporary_item_id"]

    # Merge to existing catalog item
    merge_resp = await client.post(
        f"/api/v1/temporary-items/{temp_item_id}/merge",
        headers={"X-User-Token": seed["chief_token"]},
        json={"target_item_id": seed["catalog_item_id"], "comment": "Stage 3A merge test"},
    )
    assert merge_resp.status_code == 200
    body = merge_resp.json()
    assert body["status"] == "merged_to_item"
    assert body["resolved_item_id"] == seed["catalog_item_id"]
    assert body["resolution_type"] == "merge"

    async with session_factory() as session:
        # Verify temporary item is resolved
        temp_item = await session.get(TemporaryItem, temp_item_id)
        assert temp_item is not None
        assert temp_item.status == "merged_to_item"

        # Verify backing item is deactivated
        backing_item = await session.get(Item, temp_item.item_id)
        assert backing_item is not None
        assert backing_item.is_active is False

        # Verify temporary inventory subject is archived
        temp_subject = await session.execute(
            select(InventorySubject).where(InventorySubject.temporary_item_id == temp_item_id)
        )
        temp_subject = temp_subject.scalar_one_or_none()
        assert temp_subject is not None
        assert temp_subject.archived_at is not None

        # Verify balance transferred to target subject
        target_subject = await session.execute(
            select(InventorySubject).where(InventorySubject.item_id == seed["catalog_item_id"])
        )
        target_subject = target_subject.scalar_one_or_none()
        assert target_subject is not None

        balance = await session.execute(
            select(Balance).where(
                Balance.site_id == seed["site_id"],
                Balance.inventory_subject_id == target_subject.id,
            )
        )
        balance = balance.scalar_one_or_none()
        assert balance is not None
        assert Decimal(str(balance.qty)) == Decimal("3")


@pytest.mark.asyncio
async def test_stage3a_merge_to_item_blocks_when_pending_register_exists(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Merge must be blocked if temporary item has active pending registers."""
    seed = await _seed(session_factory)

    create_resp = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "s3a-merge-block-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 2,
                    "temporary_item": {
                        "client_key": "tmp-merge-block",
                        "name": "Merge Block Test",
                        "sku": None,
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                },
            ],
        },
    )
    assert create_resp.status_code == 200
    op = create_resp.json()
    temp_item_id = op["lines"][0]["temporary_item_id"]

    # Submit (creates pending register)
    submit_resp = await client.post(
        f"/api/v1/operations/{op['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_resp.status_code == 200

    # Try to merge - should be blocked
    merge_resp = await client.post(
        f"/api/v1/temporary-items/{temp_item_id}/merge",
        headers={"X-User-Token": seed["chief_token"]},
        json={"target_item_id": seed["catalog_item_id"]},
    )
    assert merge_resp.status_code == 409
    assert "active" in merge_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_stage3a_merge_to_item_rejects_same_backing_item(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Merge must reject if target_item_id equals the backing item_id."""
    seed = await _seed(session_factory)
    result = await _create_temporary_item_with_balance(
        client, seed, "s3a-merge-self-1", "tmp-merge-self", qty=1,
    )
    temp_item_id = result["temporary_item_id"]

    # Get the backing item_id from the temporary item
    async with session_factory() as session:
        temp_item = await session.get(TemporaryItem, temp_item_id)
        assert temp_item is not None
        backing_item_id = temp_item.item_id

    merge_resp = await client.post(
        f"/api/v1/temporary-items/{temp_item_id}/merge",
        headers={"X-User-Token": seed["chief_token"]},
        json={"target_item_id": backing_item_id},
    )
    assert merge_resp.status_code == 422
    assert "must differ" in merge_resp.json()["detail"].lower()


# ============================================================
# Stage 3A: Existing Phase 1 tests still pass
# ============================================================


@pytest.mark.asyncio
async def test_stage3a_phase1_approve_still_works(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Verify that the basic approve flow (no balance to transfer) still works."""
    seed = await _seed(session_factory)

    # Create a temporary item via operation (no submit/accept, so no balance)
    create_resp = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "s3a-legacy-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 1,
                    "temporary_item": {
                        "client_key": "tmp-legacy",
                        "name": "Legacy Approve",
                        "sku": None,
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                },
            ],
        },
    )
    assert create_resp.status_code == 200
    temp_item_id = create_resp.json()["lines"][0]["temporary_item_id"]

    # Approve (no balance to transfer, should succeed)
    approve_resp = await client.post(
        f"/api/v1/temporary-items/{temp_item_id}/approve-as-item",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved_as_item"
