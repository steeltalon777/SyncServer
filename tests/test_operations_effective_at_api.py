from datetime import datetime, timezone
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
        site = Site(code=f"OPS-{suffix}", name=f"Operations Site {suffix}")
        session.add(site)
        await session.flush()

        root_user = User(
            username=f"root-{suffix}",
            email=f"root-{suffix}@example.com",
            full_name="Root User",
            is_active=True,
            is_root=True,
            role="root",
            default_site_id=site.id,
        )
        chief_user = User(
            username=f"chief-{suffix}",
            email=f"chief-{suffix}@example.com",
            full_name="Chief Storekeeper",
            is_active=True,
            is_root=False,
            role="chief_storekeeper",
            default_site_id=site.id,
        )
        storekeeper_user = User(
            username=f"storekeeper-{suffix}",
            email=f"storekeeper-{suffix}@example.com",
            full_name="Storekeeper",
            is_active=True,
            is_root=False,
            role="storekeeper",
            default_site_id=site.id,
        )
        session.add_all([root_user, chief_user, storekeeper_user])
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

        unit = Unit(code=f"PCS{suffix}", name=f"Piece {suffix}", symbol=f"P{suffix}", is_active=True)
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
        }


async def _create_operation(client: AsyncClient, *, token: str, site_id: int, item_id: int) -> dict:
    response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": token},
        json={
            "operation_type": "RECEIVE",
            "site_id": site_id,
            "lines": [{"line_number": 1, "item_id": item_id, "qty": 5}],
            "notes": "incoming",
        },
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_create_operation_sets_default_effective_at(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)

    operation = await _create_operation(
        client,
        token=seed["storekeeper_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    assert operation["effective_at"] is not None


@pytest.mark.asyncio
async def test_general_patch_rejects_effective_at_changes(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)
    operation = await _create_operation(
        client,
        token=seed["storekeeper_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    response = await client.patch(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"effective_at": datetime(2026, 1, 20, 10, 30, tzinfo=timezone.utc).isoformat()},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "effective_at must be changed via PATCH /operations/{operation_id}/effective-at"


@pytest.mark.asyncio
async def test_storekeeper_cannot_use_effective_at_endpoint(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)
    operation = await _create_operation(
        client,
        token=seed["storekeeper_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    response = await client.patch(
        f"/api/v1/operations/{operation['id']}/effective-at",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"effective_at": datetime(2026, 1, 21, 10, 30, tzinfo=timezone.utc).isoformat()},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "only chief_storekeeper or root may change operation effective_at"


@pytest.mark.asyncio
async def test_chief_storekeeper_can_change_effective_at_for_submitted_operation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)
    operation = await _create_operation(
        client,
        token=seed["storekeeper_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    submit_response = await client.post(
        f"/api/v1/operations/{operation['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_response.status_code == 200

    new_effective_at = datetime(2026, 1, 22, 9, 45, tzinfo=timezone.utc)
    update_response = await client.patch(
        f"/api/v1/operations/{operation['id']}/effective-at",
        headers={"X-User-Token": seed["chief_token"]},
        json={"effective_at": new_effective_at.isoformat()},
    )

    assert update_response.status_code == 200
    updated_operation = update_response.json()
    assert updated_operation["status"] == "submitted"
    assert datetime.fromisoformat(updated_operation["effective_at"]) == new_effective_at
