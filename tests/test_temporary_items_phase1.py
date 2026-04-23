from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.category import Category
from app.models.balance import Balance
from app.models.inventory_subject import InventorySubject
from app.models.item import Item
from app.models.operation import OperationLine
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
        observer = User(
            username=f"observer-{suffix}",
            email=f"observer-{suffix}@example.com",
            full_name="Observer",
            is_active=True,
            is_root=False,
            role="observer",
            default_site_id=site.id,
        )
        session.add_all([chief, storekeeper, observer])
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
                UserAccessScope(
                    user_id=observer.id,
                    site_id=site.id,
                    can_view=True,
                    can_operate=False,
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
            "observer_token": str(observer.user_token),
            "category_id": category.id,
            "unit_id": unit.id,
            "catalog_item_id": catalog_item.id,
        }


@pytest.mark.asyncio
async def test_receive_operation_can_create_inline_temporary_item_atomically(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)

    response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "tmp-receive-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 2,
                    "temporary_item": {
                        "client_key": "tmp-1",
                        "name": "Временный кабель",
                        "sku": None,
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                        "description": "inline create",
                        "hashtags": ["кабель"],
                    },
                },
                {
                    "line_number": 2,
                    "qty": 1,
                    "item_id": seed["catalog_item_id"],
                },
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["lines"][0]["temporary_item_id"] is not None
    assert body["lines"][0]["temporary_item_status"] == "active"
    assert body["lines"][1]["temporary_item_id"] is None

    async with session_factory() as session:
        temporary_items = list((await session.execute(select(TemporaryItem))).scalars().all())
        assert len(temporary_items) == 1
        assert temporary_items[0].name == "Временный кабель"
        backing_item = await session.get(Item, temporary_items[0].item_id)
        assert backing_item is not None
        assert backing_item.is_active is False

        lines = list((await session.execute(select(OperationLine).order_by(OperationLine.line_number))).scalars().all())
        assert len(lines) == 2
        assert lines[0].inventory_subject_id is not None
        assert lines[1].inventory_subject_id is not None

        subject_line_1 = await session.get(InventorySubject, lines[0].inventory_subject_id)
        subject_line_2 = await session.get(InventorySubject, lines[1].inventory_subject_id)
        assert subject_line_1 is not None
        assert subject_line_2 is not None
        assert subject_line_1.subject_type == "temporary_item"
        assert subject_line_2.subject_type == "catalog_item"


@pytest.mark.asyncio
async def test_receive_submit_accept_updates_balances_by_inventory_subject(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)

    create_response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "tmp-receive-write-path-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 2,
                    "temporary_item": {
                        "client_key": "tmp-1",
                        "name": "Временный кабель",
                        "sku": None,
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                },
                {
                    "line_number": 2,
                    "qty": 1,
                    "item_id": seed["catalog_item_id"],
                },
            ],
        },
    )
    assert create_response.status_code == 200
    operation = create_response.json()

    submit_response = await client.post(
        f"/api/v1/operations/{operation['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_response.status_code == 200

    accept_response = await client.post(
        f"/api/v1/operations/{operation['id']}/accept-lines",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "lines": [
                {"line_id": operation["lines"][0]["id"], "accepted_qty": 2, "lost_qty": 0},
                {"line_id": operation["lines"][1]["id"], "accepted_qty": 1, "lost_qty": 0},
            ]
        },
    )
    assert accept_response.status_code == 200

    async with session_factory() as session:
        lines = list((await session.execute(select(OperationLine).order_by(OperationLine.line_number))).scalars().all())
        assert len(lines) == 2

        balances = list(
            (
                await session.execute(
                    select(Balance)
                    .where(Balance.site_id == seed["site_id"])
                    .order_by(Balance.inventory_subject_id)
                )
            ).scalars().all()
        )
        assert len(balances) == 2

        balances_by_subject = {int(row.inventory_subject_id): row for row in balances}
        assert Decimal(str(balances_by_subject[int(lines[0].inventory_subject_id)].qty)) == Decimal("2")
        assert Decimal(str(balances_by_subject[int(lines[1].inventory_subject_id)].qty)) == Decimal("1")

        assert balances_by_subject[int(lines[0].inventory_subject_id)].item_id == lines[0].item_id
        assert balances_by_subject[int(lines[1].inventory_subject_id)].item_id == lines[1].item_id


@pytest.mark.asyncio
async def test_inline_temporary_item_requires_client_request_id_and_blocks_observer(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)

    no_request_id = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "lines": [
                {
                    "line_number": 1,
                    "qty": 1,
                    "temporary_item": {
                        "client_key": "tmp-1",
                        "name": "Без request id",
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                }
            ],
        },
    )
    assert no_request_id.status_code == 422

    forbidden = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["observer_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "observer-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 1,
                    "temporary_item": {
                        "client_key": "tmp-1",
                        "name": "Нельзя observer",
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                }
            ],
        },
    )
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_failed_inline_temporary_item_creation_rolls_back_created_entities(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)

    response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "rollback-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 1,
                    "temporary_item": {
                        "client_key": "tmp-1",
                        "name": "Откат",
                        "unit_id": seed["unit_id"],
                        "category_id": None,
                    },
                }
            ],
        },
    )

    assert response.status_code == 422

    async with session_factory() as session:
        temporary_count = len(list((await session.execute(select(TemporaryItem))).scalars().all()))
        items = list((await session.execute(select(Item).where(Item.source_system == "temporary_item"))).scalars().all())
        assert temporary_count == 0
        assert items == []


@pytest.mark.asyncio
async def test_temporary_items_review_endpoints_support_list_detail_and_phase1_resolution(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)

    create_response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": "review-1",
            "lines": [
                {
                    "line_number": 1,
                    "qty": 1,
                    "temporary_item": {
                        "client_key": "tmp-1",
                        "name": "На разбор",
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                }
            ],
        },
    )
    assert create_response.status_code == 200
    temporary_item_id = create_response.json()["lines"][0]["temporary_item_id"]

    list_response = await client.get(
        "/api/v1/temporary-items",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert list_response.status_code == 200
    assert list_response.json()["total_count"] == 1

    detail_response = await client.get(
        f"/api/v1/temporary-items/{temporary_item_id}",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "active"

    approve_response = await client.post(
        f"/api/v1/temporary-items/{temporary_item_id}/approve-as-item",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved_as_item"
    # Stage 3A: approve creates a new permanent item; backing item stays inactive
    assert approve_response.json()["resolved_item_id"] is not None
    assert approve_response.json()["resolution_type"] == "approve_as_item"
