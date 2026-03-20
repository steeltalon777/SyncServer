from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.catalog_defaults import UNCATEGORIZED_CATEGORY_CODE, UNCATEGORIZED_CATEGORY_NAME
from app.core.db import get_db
from app.models.category import Category
from app.models.item import Item
from app.models.site import Site
from app.models.unit import Unit
from app.models.user import User
from main import app


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


async def _seed_catalog_admin_fixture(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, int | str]:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"S-{suffix}", name=f"Admin Site {suffix}")
        session.add(site)
        await session.flush()

        root_user = User(
            username=f"root-{suffix}",
            email=f"root-{suffix}@example.com",
            full_name="Catalog Root",
            is_active=True,
            is_root=True,
            role="root",
            default_site_id=site.id,
        )
        session.add(root_user)

        unit = Unit(name=f"Piece-{suffix}", symbol=f"pc{suffix[:3]}", is_active=True)
        session.add(unit)
        await session.flush()

        category = Category(name=f"Tools {suffix}", code=f"TOOLS-{suffix}", is_active=True)
        session.add(category)
        await session.flush()

        item = Item(
            sku=f"SKU-{suffix}",
            name=f"Hammer {suffix}",
            category_id=category.id,
            unit_id=unit.id,
            is_active=True,
        )
        session.add(item)
        await session.commit()

        return {
            "token": str(root_user.user_token),
            "unit_id": unit.id,
            "category_id": category.id,
            "item_id": item.id,
        }


async def _get_uncategorized_category(session_factory: async_sessionmaker[AsyncSession]) -> Category:
    async with session_factory() as session:
        result = await session.execute(select(Category).where(Category.code == UNCATEGORIZED_CATEGORY_CODE))
        category = result.scalar_one()
        return category


@pytest.mark.asyncio(loop_scope="session")
async def test_create_item_falls_back_to_uncategorized_for_missing_or_invalid_category(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_catalog_admin_fixture(session_factory)

    null_category_response = await client.post(
        "/api/v1/catalog/admin/items",
        headers={"X-User-Token": seed["token"]},
        json={
            "name": "Loose item",
            "category_id": None,
            "unit_id": seed["unit_id"],
        },
    )

    assert null_category_response.status_code == 200
    null_body = null_category_response.json()
    uncategorized_category = await _get_uncategorized_category(session_factory)
    assert null_body["category_id"] == uncategorized_category.id

    invalid_category_response = await client.post(
        "/api/v1/catalog/admin/items",
        headers={"X-User-Token": seed["token"]},
        json={
            "name": "Ghost category item",
            "category_id": 999999,
            "unit_id": seed["unit_id"],
        },
    )

    assert invalid_category_response.status_code == 200
    invalid_body = invalid_category_response.json()
    assert invalid_body["category_id"] == uncategorized_category.id

    browse_response = await client.get(
        "/api/v1/catalog/read/items",
        headers={"X-User-Token": seed["token"]},
        params={"category_id": uncategorized_category.id, "page": 1, "page_size": 20},
    )

    assert browse_response.status_code == 200
    browse_body = browse_response.json()
    assert browse_body["total_count"] == 2
    assert {item["name"] for item in browse_body["items"]} == {"Loose item", "Ghost category item"}


@pytest.mark.asyncio(loop_scope="session")
async def test_update_item_category_patch_semantics_and_protect_system_category(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_catalog_admin_fixture(session_factory)

    unchanged_response = await client.patch(
        f"/api/v1/catalog/admin/items/{seed['item_id']}",
        headers={"X-User-Token": seed["token"]},
        json={"name": "Hammer renamed"},
    )

    assert unchanged_response.status_code == 200
    unchanged_body = unchanged_response.json()
    assert unchanged_body["category_id"] == seed["category_id"]

    null_category_response = await client.patch(
        f"/api/v1/catalog/admin/items/{seed['item_id']}",
        headers={"X-User-Token": seed["token"]},
        json={"category_id": None},
    )

    assert null_category_response.status_code == 200
    uncategorized_category = await _get_uncategorized_category(session_factory)
    assert null_category_response.json()["category_id"] == uncategorized_category.id

    reserved_create_response = await client.post(
        "/api/v1/catalog/admin/categories",
        headers={"X-User-Token": seed["token"]},
        json={
            "name": "Manual uncategorized",
            "code": UNCATEGORIZED_CATEGORY_CODE,
        },
    )

    assert reserved_create_response.status_code == 409

    reserved_update_response = await client.patch(
        f"/api/v1/catalog/admin/categories/{uncategorized_category.id}",
        headers={"X-User-Token": seed["token"]},
        json={"name": "Changed"},
    )

    assert reserved_update_response.status_code == 409

    categories_response = await client.get(
        "/api/v1/catalog/read/categories",
        headers={"X-User-Token": seed["token"]},
        params={"search": UNCATEGORIZED_CATEGORY_NAME, "page": 1, "page_size": 20},
    )

    assert categories_response.status_code == 200
    categories_body = categories_response.json()
    assert categories_body["total_count"] == 1
    assert categories_body["categories"][0]["code"] == UNCATEGORIZED_CATEGORY_CODE
