"""DB-backed transaction rollback tests for submit failures (TZ §12).

A failed submit must leave no trace: balances unchanged and no
`operation.submit` audit events. A submit retried after fixing the data
must succeed.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.audit_event import AuditEvent
from app.models.balance import Balance
from app.models.category import Category
from app.models.inventory_subject import InventorySubject
from app.models.item import Item
from app.models.site import Site
from app.models.unit import Unit
from app.models.user import User
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


async def _seed(session_factory: async_sessionmaker[AsyncSession], *, item_qty: str = "200.000") -> dict:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"SITE-{suffix}", name=f"Site {suffix}", is_active=True)
        session.add(site)
        await session.flush()

        root = User(
            username=f"root-{suffix}",
            email=f"root-{suffix}@example.com",
            full_name="Root Test",
            is_active=True,
            is_root=True,
            role="root",
            default_site_id=site.id,
        )
        session.add(root)
        await session.flush()

        unit = Unit(code=f"PC-{suffix}", name=f"Piece {suffix}", symbol=f"pc{suffix[:3]}", is_active=True)
        category = Category(code=f"CAT-{suffix}", name=f"Category {suffix}", normalized_name=f"category {suffix}", is_active=True)
        session.add_all([unit, category])
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
        await session.flush()

        subject = InventorySubject(subject_type="catalog_item", item_id=item.id)
        session.add(subject)
        await session.flush()

        balance = Balance(
            site_id=site.id,
            inventory_subject_id=subject.id,
            item_id=item.id,
            qty=Decimal(item_qty),
        )
        session.add(balance)
        await session.commit()

        return {
            "site_id": site.id,
            "root_token": str(root.user_token),
            "item_id": item.id,
            "inventory_subject_id": subject.id,
        }


async def _create_expense(client, seed: dict, qty: str | int) -> str:
    resp = await client.post(
        "/api/v1/operations",
        json={
            "operation_type": "EXPENSE",
            "site_id": seed["site_id"],
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": qty}],
        },
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 200, f"create failed: {resp.text}"
    return resp.json()["id"]


async def _balance_qty(session_factory, seed: dict) -> Decimal:
    async with session_factory() as session:
        row = (
            await session.execute(
                select(Balance).where(
                    Balance.site_id == seed["site_id"],
                    Balance.inventory_subject_id == seed["inventory_subject_id"],
                )
            )
        ).scalar_one_or_none()
        return Decimal(row.qty) if row is not None else Decimal("0")


async def _submit_event_count(session_factory, op_id: str) -> int:
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "operation.submit",
                    AuditEvent.entity_id == op_id,
                )
            )
        ).scalars().all()
        return len(rows)


@pytest.mark.asyncio
async def test_submit_rollback_on_insufficient_stock(client, session_factory):
    seed = await _seed(session_factory, item_qty="80.000")
    op_id = await _create_expense(client, seed, 120)

    resp = await client.post(
        f"/api/v1/operations/{op_id}/submit",
        json={"submit": True},
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["errors"][0]["code"] == "insufficient_stock"

    assert await _balance_qty(session_factory, seed) == Decimal("80.000")
    assert await _submit_event_count(session_factory, op_id) == 0


@pytest.mark.asyncio
async def test_submit_rollback_on_stale_version(client, session_factory):
    seed = await _seed(session_factory, item_qty="200.000")
    op_id = await _create_expense(client, seed, 10)

    bump = await client.patch(
        f"/api/v1/operations/{op_id}",
        json={"notes": "version bump"},
        headers={"X-User-Token": seed["root_token"]},
    )
    assert bump.status_code == 200, bump.text

    resp = await client.post(
        f"/api/v1/operations/{op_id}/submit",
        json={"submit": True, "expected_version": 1},
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["errors"][0]["code"] == "stale_version"

    assert await _balance_qty(session_factory, seed) == Decimal("200.000")
    assert await _submit_event_count(session_factory, op_id) == 0


@pytest.mark.asyncio
async def test_submit_rollback_on_wrong_state(client, session_factory):
    seed = await _seed(session_factory, item_qty="200.000")
    op_id = await _create_expense(client, seed, 10)

    cancel = await client.post(
        f"/api/v1/operations/{op_id}/cancel",
        json={"cancel": True},
        headers={"X-User-Token": seed["root_token"]},
    )
    assert cancel.status_code == 200, cancel.text

    resp = await client.post(
        f"/api/v1/operations/{op_id}/submit",
        json={"submit": True},
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["errors"][0]["code"] == "operation_in_wrong_state"

    assert await _balance_qty(session_factory, seed) == Decimal("200.000")
    assert await _submit_event_count(session_factory, op_id) == 0


@pytest.mark.asyncio
async def test_submit_repeated_after_failure_is_safe(client, session_factory):
    seed = await _seed(session_factory, item_qty="80.000")
    op_id = await _create_expense(client, seed, 120)

    failed = await client.post(
        f"/api/v1/operations/{op_id}/submit",
        json={"submit": True},
        headers={"X-User-Token": seed["root_token"]},
    )
    assert failed.status_code == 409, failed.text
    assert await _balance_qty(session_factory, seed) == Decimal("80.000")

    # Fix the operation lines to a quantity the balance can cover.
    fix = await client.patch(
        f"/api/v1/operations/{op_id}",
        json={"lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 10}]},
        headers={"X-User-Token": seed["root_token"]},
    )
    assert fix.status_code == 200, fix.text

    ok = await client.post(
        f"/api/v1/operations/{op_id}/submit",
        json={"submit": True},
        headers={"X-User-Token": seed["root_token"]},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "submitted"
    assert await _balance_qty(session_factory, seed) == Decimal("70.000")
    assert await _submit_event_count(session_factory, op_id) == 1
