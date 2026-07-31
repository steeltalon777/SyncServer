"""Backward-compatibility tests for the submit ProblemEnvelope (TZ §9.3).

Every submit domain error response must keep `detail` as a string (legacy
consumers) while `errors[]` carries the full machine-readable fields.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
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


async def _seed(session_factory: async_sessionmaker[AsyncSession], *, item_qty: str = "80.000") -> dict:
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

        unit = Unit(
            code=f"PC-{suffix}",
            name=f"Piece {suffix}",
            symbol=f"pc{suffix[:3]}",
            is_active=True,
        )
        category = Category(
            code=f"CAT-{suffix}",
            name=f"Category {suffix}",
            normalized_name=f"category {suffix}",
            is_active=True,
        )
        session.add_all([unit, category])
        await session.flush()

        item = Item(
            sku=f"SKU-{suffix}",
            name=f"Кабель {suffix}",
            normalized_name=f"кабель {suffix}",
            category_id=category.id,
            unit_id=unit.id,
            is_active=True,
        )
        session.add(item)
        await session.flush()

        subject = InventorySubject(subject_type="catalog_item", item_id=item.id)
        session.add(subject)
        await session.flush()

        session.add(
            Balance(
                site_id=site.id,
                inventory_subject_id=subject.id,
                item_id=item.id,
                qty=Decimal(item_qty),
            )
        )
        await session.commit()

        return {
            "site_id": site.id,
            "root_token": str(root.user_token),
            "item_id": item.id,
            "unit_id": unit.id,
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


async def _submit(client, seed, op_id: str, *, expected_version: int | None = None):
    body: dict = {"submit": True}
    if expected_version is not None:
        body["expected_version"] = expected_version
    return await client.post(
        f"/api/v1/operations/{op_id}/submit",
        json=body,
        headers={"X-User-Token": seed["root_token"]},
    )


@pytest.mark.asyncio
async def test_insufficient_stock_envelope_has_detail_and_errors(client, session_factory):
    seed = await _seed(session_factory, item_qty="80.000")
    op_id = await _create_expense(client, seed, 120)

    resp = await _submit(client, seed, op_id)
    assert resp.status_code == 409, resp.text
    data = resp.json()

    assert isinstance(data["detail"], str)
    assert data["errors"] and isinstance(data["errors"], list)

    first = data["errors"][0]
    assert first["code"] == "insufficient_stock"
    assert first["scope"] == "line_group"
    assert isinstance(first["operation_line_ids"], list)
    assert all(isinstance(line_id, int) for line_id in first["operation_line_ids"])
    assert first["item"]["id"] == seed["item_id"]
    assert isinstance(first["item"]["name"], str)
    assert first["stock_site"]["id"] == seed["site_id"]
    assert isinstance(first["stock_site"]["name"], str)
    assert first["required_qty"] == "120.000"
    assert first["available_qty"] == "80.000"
    assert isinstance(first["required_qty"], str)
    assert isinstance(first["available_qty"], str)
    assert first["unit"]["id"] == seed["unit_id"]
    assert isinstance(first["unit"]["name"], str)
    assert isinstance(first["unit"]["symbol"], str)


@pytest.mark.asyncio
async def test_stale_version_envelope_has_detail_and_errors(client, session_factory):
    seed = await _seed(session_factory, item_qty="200.000")
    op_id = await _create_expense(client, seed, 10)

    bump = await client.patch(
        f"/api/v1/operations/{op_id}",
        json={"notes": "version bump"},
        headers={"X-User-Token": seed["root_token"]},
    )
    assert bump.status_code == 200, bump.text

    resp = await _submit(client, seed, op_id, expected_version=1)
    assert resp.status_code == 409, resp.text
    data = resp.json()

    assert isinstance(data["detail"], str)
    assert len(data["errors"]) == 1
    first = data["errors"][0]
    assert first["code"] == "stale_version"
    assert first["scope"] == "operation"
    assert first["expected_version"] == 1
    assert first["actual_version"] == 2
    assert isinstance(first["expected_version"], int)
    assert isinstance(first["actual_version"], int)


@pytest.mark.asyncio
async def test_wrong_state_envelope_has_detail_and_errors(client, session_factory):
    seed = await _seed(session_factory, item_qty="200.000")
    op_id = await _create_expense(client, seed, 10)

    cancel = await client.post(
        f"/api/v1/operations/{op_id}/cancel",
        json={"cancel": True},
        headers={"X-User-Token": seed["root_token"]},
    )
    assert cancel.status_code == 200, cancel.text

    resp = await _submit(client, seed, op_id)
    assert resp.status_code == 409, resp.text
    data = resp.json()

    assert isinstance(data["detail"], str)
    assert len(data["errors"]) == 1
    first = data["errors"][0]
    assert first["code"] == "operation_in_wrong_state"
    assert first["scope"] == "operation"
    assert first["current_state"] == "cancelled"
    assert first["allowed_states"] == ["draft"]
    assert isinstance(first["current_state"], str)
    assert isinstance(first["allowed_states"], list)


@pytest.mark.asyncio
async def test_not_found_envelope_has_detail_and_errors(client, session_factory):
    seed = await _seed(session_factory, item_qty="200.000")

    resp = await _submit(client, seed, str(uuid4()))
    assert resp.status_code == 404, resp.text
    data = resp.json()

    assert isinstance(data["detail"], str)
    assert data["type"] == "urn:warehouse:problem:operation-not-found"
    assert data["code"] == "operation_not_found"
    assert len(data["errors"]) == 1
    first = data["errors"][0]
    assert first["code"] == "operation_not_found"
    assert first["scope"] == "operation"


@pytest.mark.asyncio
async def test_role_not_permitted_envelope_has_detail_and_errors(client, session_factory):
    seed = await _seed(session_factory, item_qty="200.000")
    op_id = await _create_expense(client, seed, 10)

    observer = User(
        username=f"obs-{uuid4().hex[:6]}",
        email=f"obs-{uuid4().hex[:6]}@example.com",
        full_name="Observer",
        is_active=True,
        is_root=False,
        role="observer",
    )
    async with session_factory() as session:
        session.add(observer)
        await session.commit()
        observer_token = str(observer.user_token)

    resp = await client.post(
        f"/api/v1/operations/{op_id}/submit",
        json={"submit": True},
        headers={"X-User-Token": observer_token},
    )
    assert resp.status_code == 403, resp.text
    data = resp.json()

    assert isinstance(data["detail"], str)
    assert data["code"] == "operation_submit_rejected"
    assert len(data["errors"]) == 1
    first = data["errors"][0]
    assert first["code"] == "role_not_permitted"
    assert first["scope"] == "operation"
    assert set(first.keys()) == {"code", "scope"}
