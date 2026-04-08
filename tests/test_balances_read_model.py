from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.balance import Balance
from app.models.category import Category
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


async def _seed_balances_fixture(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, int | str]:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"S-{suffix}", name=f"Main Site {suffix}")
        other_site = Site(code=f"S2-{suffix}", name=f"Reserve Site {suffix}")
        session.add_all([site, other_site])
        await session.flush()

        user = User(
            username=f"chief-{suffix}",
            email=f"chief-{suffix}@example.com",
            full_name="Chief Storekeeper",
            is_active=True,
            is_root=False,
            role="chief_storekeeper",
            default_site_id=site.id,
        )
        session.add(user)

        unit = Unit(name=f"Piece-{suffix}", symbol=f"pc{suffix[:3]}", is_active=True)
        session.add(unit)
        await session.flush()

        milk_category = Category(name=f"Milk {suffix}", code=f"MILK-{suffix}", is_active=True)
        tools_category = Category(name=f"Tools {suffix}", code=f"TOOLS-{suffix}", is_active=True)
        session.add_all([milk_category, tools_category])
        await session.flush()

        milk_item = Item(
            sku=f"MILK-{suffix}",
            name=f"Whole Milk {suffix}",
            category_id=milk_category.id,
            unit_id=unit.id,
            is_active=True,
        )
        tool_item = Item(
            sku=f"TOOL-{suffix}",
            name=f"Hammer {suffix}",
            category_id=tools_category.id,
            unit_id=unit.id,
            is_active=True,
        )
        session.add_all([milk_item, tool_item])
        await session.flush()

        session.add_all(
            [
                Balance(site_id=site.id, item_id=milk_item.id, qty=7),
                Balance(site_id=other_site.id, item_id=tool_item.id, qty=3),
            ]
        )
        await session.commit()

        return {
            "token": str(user.user_token),
            "milk_category_id": milk_category.id,
            "milk_item_name": milk_item.name,
            "milk_sku": milk_item.sku or "",
            "site_name": site.name,
            "unit_symbol": unit.symbol,
            "category_name": milk_category.name,
        }


@pytest.mark.asyncio(loop_scope="session")
async def test_balances_read_model_returns_ui_ready_rows_and_filters(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_balances_fixture(session_factory)

    response = await client.get(
        "/api/v1/balances",
        headers={"X-User-Token": seed["token"]},
        params={
            "search": "Milk",
            "category_id": seed["milk_category_id"],
            "page": 1,
            "page_size": 20,
            "only_positive": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    row = body["items"][0]
    assert row["site_name"] == seed["site_name"]
    assert row["item_name"] == seed["milk_item_name"]
    assert row["sku"] == seed["milk_sku"]
    assert row["unit_symbol"] == seed["unit_symbol"]
    assert row["category_name"] == seed["category_name"]
    assert row["qty"] == "7"
