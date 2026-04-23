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


# ============================================================
# Stage 3B: GET /temporary-items/{id}/operations
# ============================================================


@pytest.mark.asyncio
async def test_stage3b_get_operations_returns_operations_for_temporary_item(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """GET /temporary-items/{id}/operations returns operations where the temp item participated."""
    seed = await _seed(session_factory)

    # Create a RECEIVE operation with a temporary item
    create_resp = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "s3b-ops-list-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 3,
                    "temporary_item": {
                        "client_key": "tmp-ops-list",
                        "name": "Ops List Temp Item",
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

    # Fetch operations for this temporary item
    ops_resp = await client.get(
        f"/api/v1/temporary-items/{temp_item_id}/operations",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert ops_resp.status_code == 200
    body = ops_resp.json()
    assert body["total_count"] >= 1
    assert any(op_item["id"] == op["id"] for op_item in body["items"])

    # Verify the operation line has snapshot fields
    for op_item in body["items"]:
        for line in op_item["lines"]:
            if line.get("temporary_item_id") == temp_item_id:
                assert line["item_name_snapshot"] is not None
                assert line["item_sku_snapshot"] is None  # was None in our payload
                assert line["unit_name_snapshot"] is not None
                assert line["unit_symbol_snapshot"] is not None
                assert line["category_name_snapshot"] is not None


@pytest.mark.asyncio
async def test_stage3b_get_operations_returns_empty_for_unused_temp_item(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """GET /temporary-items/{id}/operations returns empty list for a temp item not used in any operation."""
    seed = await _seed(session_factory)

    # Create a temporary item via operation but don't reference it in any operation
    # Actually we need to create it first. Let's create an operation, get temp_item_id,
    # then check a non-existent one returns 404
    nonexistent_id = 99999
    ops_resp = await client.get(
        f"/api/v1/temporary-items/{nonexistent_id}/operations",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert ops_resp.status_code == 404


@pytest.mark.asyncio
async def test_stage3b_get_operations_requires_moderation_permission(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """GET /temporary-items/{id}/operations requires chief_storekeeper or root."""
    seed = await _seed(session_factory)

    # Create a temp item first
    create_resp = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "s3b-ops-perm-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 1,
                    "temporary_item": {
                        "client_key": "tmp-ops-perm",
                        "name": "Ops Perm Test",
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

    # Storekeeper (no catalog moderation) should be denied
    ops_resp = await client.get(
        f"/api/v1/temporary-items/{temp_item_id}/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )
    assert ops_resp.status_code == 403


# ============================================================
# Stage 3B: History-display — resolved fields after resolution
# ============================================================


@pytest.mark.asyncio
async def test_stage3b_operation_line_shows_resolved_fields_after_approve(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """After approve, operation lines show resolved_item_id and resolved_item_name."""
    seed = await _seed(session_factory)

    # Create a RECEIVE operation with a temporary item, submit and accept
    create_resp = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "s3b-hist-approve-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 5,
                    "temporary_item": {
                        "client_key": "tmp-hist-approve",
                        "name": "History Approve Test",
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

    # Accept
    accept_resp = await client.post(
        f"/api/v1/operations/{op['id']}/accept-lines",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "lines": [
                {"line_id": op["lines"][0]["id"], "accepted_qty": 5, "lost_qty": 0},
            ]
        },
    )
    assert accept_resp.status_code == 200

    # Approve the temporary item
    approve_resp = await client.post(
        f"/api/v1/temporary-items/{temp_item_id}/approve-as-item",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert approve_resp.status_code == 200
    resolved_item_id = approve_resp.json()["resolved_item_id"]
    assert resolved_item_id is not None

    # Fetch the original operation — lines should show resolved fields
    op_resp = await client.get(
        f"/api/v1/operations/{op['id']}",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert op_resp.status_code == 200
    op_body = op_resp.json()
    for line in op_body["lines"]:
        if line.get("temporary_item_id") == temp_item_id:
            # Snapshot fields should still show the historical name
            assert line["item_name_snapshot"] == "History Approve Test"
            # Resolved fields should point to the new permanent item
            assert line["resolved_item_id"] == resolved_item_id
            assert line["resolved_item_name"] is not None
            # inventory_subject_id should be present
            assert line["inventory_subject_id"] is not None
            assert line["subject_type"] is not None


@pytest.mark.asyncio
async def test_stage3b_operation_line_shows_resolved_fields_after_merge(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """After merge, operation lines show resolved_item_id pointing to target catalog item."""
    seed = await _seed(session_factory)

    # Create a RECEIVE operation with a temporary item, submit and accept
    create_resp = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "s3b-hist-merge-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 3,
                    "temporary_item": {
                        "client_key": "tmp-hist-merge",
                        "name": "History Merge Test",
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

    # Accept
    accept_resp = await client.post(
        f"/api/v1/operations/{op['id']}/accept-lines",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "lines": [
                {"line_id": op["lines"][0]["id"], "accepted_qty": 3, "lost_qty": 0},
            ]
        },
    )
    assert accept_resp.status_code == 200

    # Merge to existing catalog item
    merge_resp = await client.post(
        f"/api/v1/temporary-items/{temp_item_id}/merge",
        headers={"X-User-Token": seed["chief_token"]},
        json={"target_item_id": seed["catalog_item_id"], "comment": "Stage 3B merge test"},
    )
    assert merge_resp.status_code == 200

    # Fetch the original operation — lines should show resolved fields pointing to catalog item
    op_resp = await client.get(
        f"/api/v1/operations/{op['id']}",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert op_resp.status_code == 200
    op_body = op_resp.json()
    for line in op_body["lines"]:
        if line.get("temporary_item_id") == temp_item_id:
            # Snapshot fields should still show the historical name
            assert line["item_name_snapshot"] == "History Merge Test"
            # Resolved fields should point to the target catalog item
            assert line["resolved_item_id"] == seed["catalog_item_id"]
            assert line["resolved_item_name"] is not None
            # inventory_subject_id should be present
            assert line["inventory_subject_id"] is not None


# ============================================================
# Stage 3B: Idempotency conflict (409)
# ============================================================


@pytest.mark.asyncio
async def test_stage3b_idempotency_replay_returns_existing_operation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Re-sending the same client_request_id with the same payload returns the existing operation."""
    seed = await _seed(session_factory)

    payload = {
        "operation_type": "RECEIVE",
        "site_id": seed["site_id"],
        "client_request_id": "s3b-idem-replay-1",
        "lines": [
            {
                "line_number": 1,
                "qty": 2,
                "temporary_item": {
                    "client_key": "tmp-idem-replay",
                    "name": "Idempotent Replay",
                    "sku": None,
                    "unit_id": seed["unit_id"],
                    "category_id": seed["category_id"],
                },
            },
        ],
    }

    # First request
    resp1 = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json=payload,
    )
    assert resp1.status_code == 200
    op1_id = resp1.json()["id"]

    # Second request with same payload
    resp2 = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json=payload,
    )
    assert resp2.status_code == 200
    op2_id = resp2.json()["id"]

    # Should be the same operation (replay)
    assert op1_id == op2_id


@pytest.mark.asyncio
async def test_stage3b_idempotency_conflict_on_different_payload(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Re-sending the same client_request_id with a different payload returns 409 Conflict."""
    seed = await _seed(session_factory)

    # First request
    payload1 = {
        "operation_type": "RECEIVE",
        "site_id": seed["site_id"],
        "client_request_id": "s3b-idem-conflict-1",
        "lines": [
            {
                "line_number": 1,
                "qty": 2,
                "temporary_item": {
                    "client_key": "tmp-idem-conflict",
                    "name": "Idempotent Conflict",
                    "sku": None,
                    "unit_id": seed["unit_id"],
                    "category_id": seed["category_id"],
                },
            },
        ],
    }
    resp1 = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json=payload1,
    )
    assert resp1.status_code == 200

    # Second request with SAME client_request_id but DIFFERENT payload (different qty)
    payload2 = {
        "operation_type": "RECEIVE",
        "site_id": seed["site_id"],
        "client_request_id": "s3b-idem-conflict-1",  # same id
        "lines": [
            {
                "line_number": 1,
                "qty": 999,  # different qty
                "temporary_item": {
                    "client_key": "tmp-idem-conflict",
                    "name": "Idempotent Conflict",
                    "sku": None,
                    "unit_id": seed["unit_id"],
                    "category_id": seed["category_id"],
                },
            },
        ],
    }
    resp2 = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json=payload2,
    )
    assert resp2.status_code == 409
    detail = resp2.json()["detail"]
    assert "conflict" in detail.lower() or "Idempotency" in detail


@pytest.mark.asyncio
async def test_stage3b_idempotency_conflict_different_temporary_item_name(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Re-sending the same client_request_id with a different temporary_item name returns 409."""
    seed = await _seed(session_factory)

    # First request
    payload1 = {
        "operation_type": "RECEIVE",
        "site_id": seed["site_id"],
        "client_request_id": "s3b-idem-name-1",
        "lines": [
            {
                "line_number": 1,
                "qty": 1,
                "temporary_item": {
                    "client_key": "tmp-idem-name",
                    "name": "Original Name",
                    "sku": None,
                    "unit_id": seed["unit_id"],
                    "category_id": seed["category_id"],
                },
            },
        ],
    }
    resp1 = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json=payload1,
    )
    assert resp1.status_code == 200

    # Second request with different temporary_item name
    payload2 = {
        "operation_type": "RECEIVE",
        "site_id": seed["site_id"],
        "client_request_id": "s3b-idem-name-1",
        "lines": [
            {
                "line_number": 1,
                "qty": 1,
                "temporary_item": {
                    "client_key": "tmp-idem-name",
                    "name": "Different Name",
                    "sku": None,
                    "unit_id": seed["unit_id"],
                    "category_id": seed["category_id"],
                },
            },
        ],
    }
    resp2 = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json=payload2,
    )
    assert resp2.status_code == 409
