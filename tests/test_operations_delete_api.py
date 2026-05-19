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


async def _seed_fixture(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"DEL-{suffix}", name=f"Delete Test Site {suffix}")
        session.add(site)
        await session.flush()

        root_user = User(
            username=f"root-del-{suffix}",
            email=f"root-del-{suffix}@example.com",
            full_name="Root User",
            is_active=True,
            is_root=True,
            role="root",
            default_site_id=site.id,
        )
        chief_user = User(
            username=f"chief-del-{suffix}",
            email=f"chief-del-{suffix}@example.com",
            full_name="Chief Storekeeper",
            is_active=True,
            is_root=False,
            role="chief_storekeeper",
            default_site_id=site.id,
        )
        storekeeper_user = User(
            username=f"storekeeper-del-{suffix}",
            email=f"storekeeper-del-{suffix}@example.com",
            full_name="Storekeeper",
            is_active=True,
            is_root=False,
            role="storekeeper",
            default_site_id=site.id,
        )
        observer_user = User(
            username=f"observer-del-{suffix}",
            email=f"observer-del-{suffix}@example.com",
            full_name="Observer",
            is_active=True,
            is_root=False,
            role="observer",
            default_site_id=site.id,
        )
        session.add_all([root_user, chief_user, storekeeper_user, observer_user])
        await session.flush()

        session.add(
            UserAccessScope(
                user_id=storekeeper_user.id,
                site_id=site.id,
                can_view=True,
                can_operate=True,
                can_manage_catalog=False,
                is_active=True,
            )
        )
        session.add(
            UserAccessScope(
                user_id=observer_user.id,
                site_id=site.id,
                can_view=True,
                can_operate=False,
                can_manage_catalog=False,
                is_active=True,
            )
        )

        unit = Unit(code=f"PCS-{suffix}", name=f"Piece {suffix}", symbol=f"P{suffix}", is_active=True)
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
            "root_token": str(root_user.user_token),
            "chief_token": str(chief_user.user_token),
            "storekeeper_token": str(storekeeper_user.user_token),
            "observer_token": str(observer_user.user_token),
        }


async def _create_draft(client: AsyncClient, *, token: str, site_id: int, item_id: int) -> dict:
    response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": token},
        json={
            "operation_type": "RECEIVE",
            "site_id": site_id,
            "lines": [{"line_number": 1, "item_id": item_id, "qty": 5}],
        },
    )
    assert response.status_code == 200
    return response.json()


async def _cancel_operation(client: AsyncClient, *, token: str, operation_id: str) -> dict:
    response = await client.post(
        f"/api/v1/operations/{operation_id}/cancel",
        headers={"X-User-Token": token},
        json={"cancel": True, "reason": "test cancel"},
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_delete_cancelled_operation_returns_204(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)
    operation = await _create_draft(client, token=seed["storekeeper_token"], site_id=seed["site_id"], item_id=seed["item_id"])
    await _cancel_operation(client, token=seed["storekeeper_token"], operation_id=operation["id"])

    response = await client.delete(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_cancelled_operation_removes_from_list(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)
    operation = await _create_draft(client, token=seed["storekeeper_token"], site_id=seed["site_id"], item_id=seed["item_id"])
    await _cancel_operation(client, token=seed["storekeeper_token"], operation_id=operation["id"])

    await client.delete(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )

    list_response = await client.get(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )
    items = list_response.json()["items"]
    ids = [item["id"] for item in items]
    assert operation["id"] not in ids


@pytest.mark.asyncio
async def test_delete_cancelled_operation_removes_from_get(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)
    operation = await _create_draft(client, token=seed["storekeeper_token"], site_id=seed["site_id"], item_id=seed["item_id"])
    await _cancel_operation(client, token=seed["storekeeper_token"], operation_id=operation["id"])

    await client.delete(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )

    get_response = await client.get(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_draft_operation_returns_409(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)
    operation = await _create_draft(client, token=seed["storekeeper_token"], site_id=seed["site_id"], item_id=seed["item_id"])

    response = await client.delete(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_delete_submitted_operation_returns_409(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)
    operation = await _create_draft(client, token=seed["storekeeper_token"], site_id=seed["site_id"], item_id=seed["item_id"])

    submit_response = await client.post(
        f"/api/v1/operations/{operation['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_response.status_code == 200

    response = await client.delete(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["chief_token"]},
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_delete_missing_operation_returns_404(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)

    response = await client.delete(
        f"/api/v1/operations/{uuid4()}",
        headers={"X-User-Token": seed["root_token"]},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_observer_cannot_delete_cancelled_operation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)
    operation = await _create_draft(client, token=seed["storekeeper_token"], site_id=seed["site_id"], item_id=seed["item_id"])
    await _cancel_operation(client, token=seed["storekeeper_token"], operation_id=operation["id"])

    response = await client.delete(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["observer_token"]},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_storekeeper_cannot_delete_other_creators_cancelled_operation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)
    operation = await _create_draft(client, token=seed["chief_token"], site_id=seed["site_id"], item_id=seed["item_id"])
    await _cancel_operation(client, token=seed["chief_token"], operation_id=operation["id"])

    response = await client.delete(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_chief_storekeeper_can_delete_any_cancelled_operation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)
    operation = await _create_draft(client, token=seed["storekeeper_token"], site_id=seed["site_id"], item_id=seed["item_id"])
    await _cancel_operation(client, token=seed["storekeeper_token"], operation_id=operation["id"])

    response = await client.delete(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["chief_token"]},
    )

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_root_can_delete_any_cancelled_operation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)
    operation = await _create_draft(client, token=seed["storekeeper_token"], site_id=seed["site_id"], item_id=seed["item_id"])
    await _cancel_operation(client, token=seed["storekeeper_token"], operation_id=operation["id"])

    response = await client.delete(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["root_token"]},
    )

    assert response.status_code == 204
