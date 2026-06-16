from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.balance import Balance
from app.models.category import Category
from app.models.inventory_subject import InventorySubject
from app.models.item import Item
from app.models.site import Site
from app.models.unit import Unit
from app.models.user import User
from main import create_app

app = create_app(enable_startup_migrations=False)


async def _seed_with_balance(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    item_qty: str = "10.000",
    second_site: bool = False,
) -> dict:
    """Create seed data: site, root user, category, unit, item, inventory_subject, balance."""
    async with session_factory() as session:
        site = Site(
            code=f"SITE-{uuid4().hex[:6]}",
            name=f"Test Site {uuid4().hex[:4]}",
            is_active=True,
        )
        session.add(site)
        await session.flush()

        second_site_obj = None
        if second_site:
            second_site_obj = Site(
                code=f"SITE-{uuid4().hex[:6]}",
                name=f"Dest Site {uuid4().hex[:4]}",
                is_active=True,
            )
            session.add(second_site_obj)
            await session.flush()

        root_user = User(
            username=f"root-{uuid4().hex[:6]}",
            email=f"root-{uuid4().hex[:6]}@example.com",
            full_name="Root Test",
            is_active=True,
            is_root=True,
            role="root",
        )
        session.add(root_user)
        await session.flush()

        unit = Unit(name=f"pcs-{uuid4().hex[:4]}", symbol=f"p{uuid4().hex[:2]}", is_active=True)
        session.add(unit)
        await session.flush()

        category = Category(name=f"cat-{uuid4().hex[:4]}", is_active=True)
        session.add(category)
        await session.flush()

        item = Item(
            sku=f"SKU-{uuid4().hex[:6]}",
            name=f"Test Item {uuid4().hex[:4]}",
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

        result = {
            "site_id": site.id,
            "root_token": str(root_user.user_token),
            "item_id": item.id,
            "inventory_subject_id": subject.id,
        }

        if second_site and second_site_obj is not None:
            result["second_site_id"] = second_site_obj.id

        return result


@pytest.fixture
async def client(session_factory: async_sessionmaker[AsyncSession]):
    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.rollback()

    app.dependency_overrides[get_db] = override_get_db
    from httpx import ASGITransport, AsyncClient
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_expense_rejects_stale_balance(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """EXPENSE submit fails when balance changed after first operation consumed it."""
    seed = await _seed_with_balance(session_factory, item_qty="10.000")
    root_headers = {"X-User-Token": seed["root_token"]}
    site_id = seed["site_id"]
    item_id = seed["item_id"]

    # Create and submit first EXPENSE — consumes all 10 units
    draft_payload = {
        "type": "EXPENSE",
        "site_id": site_id,
        "lines": [{"item_id": item_id, "qty": "10.000", "line_number": 1}],
    }
    draft_resp = await client.post("/api/v1/operations", json=draft_payload, headers=root_headers)
    assert draft_resp.status_code == 200, f"create failed: {draft_resp.text}"
    op1_id = draft_resp.json()["id"]

    submit1 = await client.post(f"/api/v1/operations/{op1_id}/submit", json={"submit": True}, headers=root_headers)
    assert submit1.status_code == 200, f"first submit failed: {submit1.text}"

    # Create second EXPENSE with same qty — balance is now 0
    draft2_payload = {
        "type": "EXPENSE",
        "site_id": site_id,
        "lines": [{"item_id": item_id, "qty": "10.000", "line_number": 1}],
    }
    draft2_resp = await client.post("/api/v1/operations", json=draft2_payload, headers=root_headers)
    assert draft2_resp.status_code == 200, f"second create failed: {draft2_resp.text}"
    op2_id = draft2_resp.json()["id"]

    # Submit should fail with 409 Conflict
    submit2 = await client.post(f"/api/v1/operations/{op2_id}/submit", json={"submit": True}, headers=root_headers)
    assert submit2.status_code == 409, f"expected 409, got {submit2.status_code}: {submit2.text}"
    data = submit2.json()
    detail = data.get("detail") or ""
    assert "insufficient" in detail.lower(), f"expected insufficient stock message, got: {detail}"


@pytest.mark.asyncio
async def test_move_rejects_stale_balance(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """MOVE submit fails when source balance changed after first move consumed it."""
    seed = await _seed_with_balance(session_factory, item_qty="5.000", second_site=True)
    root_headers = {"X-User-Token": seed["root_token"]}
    source_site_id = seed["site_id"]
    dest_site_id = seed["second_site_id"]
    item_id = seed["item_id"]

    # Create and submit first MOVE — consumes all 5 units from source
    move_payload = {
        "type": "MOVE",
        "site_id": source_site_id,
        "source_site_id": source_site_id,
        "destination_site_id": dest_site_id,
        "lines": [{"item_id": item_id, "qty": "5.000", "line_number": 1}],
    }
    draft_resp = await client.post("/api/v1/operations", json=move_payload, headers=root_headers)
    assert draft_resp.status_code == 200, f"create move failed: {draft_resp.text}"
    op1_id = draft_resp.json()["id"]

    submit1 = await client.post(f"/api/v1/operations/{op1_id}/submit", json={"submit": True}, headers=root_headers)
    assert submit1.status_code == 200, f"first move submit failed: {submit1.text}"

    # Create second MOVE with same qty — source balance is now 0
    move2_payload = {
        "type": "MOVE",
        "site_id": source_site_id,
        "source_site_id": source_site_id,
        "destination_site_id": dest_site_id,
        "lines": [{"item_id": item_id, "qty": "5.000", "line_number": 1}],
    }
    draft2_resp = await client.post("/api/v1/operations", json=move2_payload, headers=root_headers)
    assert draft2_resp.status_code == 200, f"second move create failed: {draft2_resp.text}"
    op2_id = draft2_resp.json()["id"]

    # Submit should fail with 409 Conflict
    submit2 = await client.post(f"/api/v1/operations/{op2_id}/submit", json={"submit": True}, headers=root_headers)
    assert submit2.status_code == 409, f"expected 409, got {submit2.status_code}: {submit2.text}"
    data = submit2.json()
    detail = data.get("detail") or ""
    assert "insufficient" in detail.lower(), f"expected insufficient stock message, got: {detail}"
