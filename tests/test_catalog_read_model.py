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


async def _seed_catalog_read_fixture(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"S-{uuid4().hex[:6]}", name="Catalog Site")
        session.add(site)
        await session.flush()

        user = User(
            username=f"observer-{uuid4().hex[:6]}",
            email=f"observer-{uuid4().hex[:6]}@example.com",
            full_name="Catalog Observer",
            is_active=True,
            is_root=False,
            role="observer",
            default_site_id=site.id,
        )
        session.add(user)
        await session.flush()

        scope = UserAccessScope(
            user_id=user.id,
            site_id=site.id,
            can_view=True,
            can_operate=False,
            can_manage_catalog=False,
            is_active=True,
        )
        session.add(scope)

        unit_liter = Unit(name=f"Liter-{suffix}", symbol=f"l{suffix[:3]}", is_active=True)
        unit_piece = Unit(name=f"Piece-{suffix}", symbol=f"p{suffix[:3]}", is_active=True)
        session.add_all([unit_liter, unit_piece])
        await session.flush()

        root_name = f"Food {suffix}"
        milk_name = f"Milk {suffix}"
        cheese_name = f"Cheese {suffix}"
        whole_milk_name = f"Whole Milk {suffix}"
        whole_milk_item_name = f"Whole Milk 1L {suffix}"
        farm_milk_item_name = f"Farm Milk 2L {suffix}"
        milk_search_term = f"MILK-{suffix}"

        root = Category(name=root_name, code=f"FOOD-{suffix}", sort_order=1, is_active=True)
        session.add(root)
        await session.flush()

        milk = Category(name=milk_name, code=f"MILK-{suffix}", parent_id=root.id, sort_order=1, is_active=True)
        cheese = Category(name=cheese_name, code=f"CHEESE-{suffix}", parent_id=root.id, sort_order=2, is_active=True)
        archived = Category(name=f"Archived {suffix}", code=f"ARCH-{suffix}", parent_id=root.id, sort_order=3, is_active=False)
        session.add_all([milk, cheese, archived])
        await session.flush()

        whole_milk = Category(
            name=whole_milk_name,
            code=f"MILK-WHOLE-{suffix}",
            parent_id=milk.id,
            sort_order=1,
            is_active=True,
        )
        session.add(whole_milk)
        await session.flush()

        items = [
            Item(
                sku=f"{milk_search_term}-001",
                name=whole_milk_item_name,
                category_id=whole_milk.id,
                unit_id=unit_liter.id,
                description="Shelf item",
                is_active=True,
            ),
            Item(
                sku=f"{milk_search_term}-002",
                name=farm_milk_item_name,
                category_id=milk.id,
                unit_id=unit_liter.id,
                description="Fresh delivery",
                is_active=True,
            ),
            Item(
                sku=f"CHEESE-001-{suffix}",
                name=f"Cheese Wheel {suffix}",
                category_id=cheese.id,
                unit_id=unit_piece.id,
                description="Aged cheese",
                is_active=True,
            ),
            Item(
                sku=f"{milk_search_term}-999",
                name=f"Old Milk {suffix}",
                category_id=milk.id,
                unit_id=unit_liter.id,
                description="Inactive item",
                is_active=False,
            ),
        ]
        session.add_all(items)
        await session.commit()

        return {
            "token": str(user.user_token),
            "root_id": root.id,
            "milk_id": milk.id,
            "whole_milk_id": whole_milk.id,
            "root_name": root_name,
            "milk_name": milk_name,
            "cheese_name": cheese_name,
            "whole_milk_name": whole_milk_name,
            "whole_milk_item_name": whole_milk_item_name,
            "farm_milk_item_name": farm_milk_item_name,
            "milk_search_term": milk_search_term,
            "unit_liter_symbol": unit_liter.symbol,
        }


@pytest.mark.asyncio(loop_scope="session")
async def test_catalog_read_categories_returns_row_ready_data(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_catalog_read_fixture(session_factory)

    response = await client.get(
        "/api/v1/catalog/read/categories",
        headers={"X-User-Token": seed["token"]},
        params={"search": "Whole", "page": 1, "page_size": 10},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 10

    category = body["categories"][0]
    assert category["name"] == seed["whole_milk_name"]
    assert category["parent"]["name"] == seed["milk_name"]
    assert [node["name"] for node in category["parent_chain_summary"]] == [seed["root_name"], seed["milk_name"]]
    assert category["items_count"] == 1
    assert category["children_count"] == 0
    assert [item["name"] for item in category["items_preview"]] == [seed["whole_milk_item_name"]]

    parent_only_response = await client.get(
        "/api/v1/catalog/read/categories",
        headers={"X-User-Token": seed["token"]},
        params={
            "parent_id": seed["root_id"],
            "include": "parent",
            "page": 1,
            "page_size": 10,
        },
    )

    assert parent_only_response.status_code == 200
    parent_only_body = parent_only_response.json()
    assert parent_only_body["total_count"] == 2
    names = [row["name"] for row in parent_only_body["categories"]]
    assert names == [seed["milk_name"], seed["cheese_name"]]
    assert all(row["parent"]["name"] == seed["root_name"] for row in parent_only_body["categories"])
    assert all(row["parent_chain_summary"] == [] for row in parent_only_body["categories"])
    assert all(row["items_preview"] == [] for row in parent_only_body["categories"])


@pytest.mark.asyncio(loop_scope="session")
async def test_catalog_read_items_children_and_parent_chain(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_catalog_read_fixture(session_factory)

    items_response = await client.get(
        "/api/v1/catalog/read/items",
        headers={"X-User-Token": seed["token"]},
        params={"search": seed["milk_search_term"], "page": 1, "page_size": 10},
    )

    assert items_response.status_code == 200
    items_body = items_response.json()
    assert items_body["total_count"] == 2
    assert [item["name"] for item in items_body["items"]] == [seed["farm_milk_item_name"], seed["whole_milk_item_name"]]
    assert all(item["unit_symbol"] == seed["unit_liter_symbol"] for item in items_body["items"])

    children_response = await client.get(
        f"/api/v1/catalog/read/categories/{seed['milk_id']}/children",
        headers={"X-User-Token": seed["token"]},
        params={"page": 1, "page_size": 10, "items_preview_limit": 1},
    )

    assert children_response.status_code == 200
    children_body = children_response.json()
    assert children_body["total_count"] == 1
    assert children_body["categories"][0]["name"] == seed["whole_milk_name"]
    assert [item["name"] for item in children_body["categories"][0]["items_preview"]] == [seed["whole_milk_item_name"]]

    category_items_response = await client.get(
        f"/api/v1/catalog/read/categories/{seed['whole_milk_id']}/items",
        headers={"X-User-Token": seed["token"]},
        params={"page": 1, "page_size": 10},
    )

    assert category_items_response.status_code == 200
    category_items_body = category_items_response.json()
    assert category_items_body["total_count"] == 1
    assert category_items_body["items"][0]["name"] == seed["whole_milk_item_name"]
    assert category_items_body["items"][0]["category_name"] == seed["whole_milk_name"]

    parent_chain_response = await client.get(
        f"/api/v1/catalog/read/categories/{seed['whole_milk_id']}/parent-chain",
        headers={"X-User-Token": seed["token"]},
    )

    assert parent_chain_response.status_code == 200
    parent_chain_body = parent_chain_response.json()
    assert parent_chain_body["category_id"] == seed["whole_milk_id"]
    assert [node["name"] for node in parent_chain_body["parent_chain_summary"]] == [seed["root_name"], seed["milk_name"]]
