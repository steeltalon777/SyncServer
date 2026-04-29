from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.routes_balances import _resolve_visible_site_ids
from app.core.identity import Identity
from app.core.db import get_db
from app.models.site import Site
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
    """Создаёт root пользователя и активный сайт, возвращает словарь с идентификаторами."""
    async with session_factory() as session:
        # Создаём активный сайт
        site = Site(
            code=f"SITE-{uuid4().hex[:6]}",
            name=f"Test Site {uuid4().hex[:4]}",
            is_active=True,
        )
        session.add(site)
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
        await session.commit()

        return {
            "site_id": site.id,
            "root_token": str(root_user.user_token),
        }


@pytest.fixture
async def root_headers(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, str]:
    """Фикстура, возвращающая заголовки аутентификации для root пользователя."""
    seed = await _seed_fixture(session_factory)
    return {"X-User-Token": seed["root_token"]}


@pytest.mark.asyncio
async def test_balances_endpoint(
    client: AsyncClient,
    root_headers: dict[str, str],
) -> None:
    """GET /api/v1/balances возвращает корректную структуру."""
    response = await client.get("/api/v1/balances", headers=root_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total_count" in data
    assert "page" in data
    assert "page_size" in data
    assert isinstance(data["items"], list)
    assert isinstance(data["total_count"], int)
    assert data["total_count"] >= 0
    assert data["page"] == 1
    assert data["page_size"] == 100


@pytest.mark.asyncio
async def test_balance_read_site_ids_include_all_sites_regardless_of_scope() -> None:
    user = User(
        username=f"storekeeper-{uuid4().hex[:6]}",
        email=f"storekeeper-{uuid4().hex[:6]}@example.com",
        full_name="Storekeeper",
        is_active=True,
        is_root=False,
        role="storekeeper",
        default_site_id=None,
    )
    identity = Identity.from_user_and_device(
        user=user,
        device=None,
        scopes=[
            UserAccessScope(
                user_id=uuid4(),
                site_id=10,
                can_view=True,
                can_operate=True,
                can_manage_catalog=False,
                is_active=True,
            )
        ],
    )

    class SitesRepo:
        async def list_sites(self, **kwargs):
            return [Site(id=10, code="A", name="A"), Site(id=999, code="B", name="B")], 2

    uow = type("FakeUow", (), {"sites": SitesRepo()})()

    site_ids = await _resolve_visible_site_ids(uow, identity)

    assert site_ids == [10, 999]


@pytest.mark.asyncio
async def test_balances_by_site(
    client: AsyncClient,
    root_headers: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """GET /api/v1/balances/by-site?site_id=... возвращает только items для указанного site_id."""
    # Получаем site_id из фикстуры
    seed = await _seed_fixture(session_factory)
    site_id = seed["site_id"]

    response = await client.get(
        f"/api/v1/balances/by-site?site_id={site_id}",
        headers=root_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    # Проверяем, что каждый item имеет site_id = запрошенному
    for item in data["items"]:
        assert item["site_id"] == site_id


@pytest.mark.asyncio
async def test_balances_summary(
    client: AsyncClient,
    root_headers: dict[str, str],
) -> None:
    """GET /api/v1/balances/summary возвращает summary с корректными полями."""
    response = await client.get("/api/v1/balances/summary", headers=root_headers)
    assert response.status_code == 200
    data = response.json()
    assert "accessible_sites_count" in data
    assert "summary" in data
    summary = data["summary"]
    assert "rows_count" in summary
    assert "sites_count" in summary
    assert "total_quantity" in summary

    # Проверяем типы и ограничения
    assert isinstance(summary["rows_count"], int)
    assert summary["rows_count"] >= 0
    assert isinstance(summary["sites_count"], int)
    assert summary["sites_count"] >= 0
    # total_quantity может быть float (в схеме float), но должен быть >= 0
    total_qty = summary["total_quantity"]
    assert isinstance(total_qty, (int, float))
    assert total_qty >= 0


@pytest.mark.asyncio
async def test_consistency_item_acb(
    client: AsyncClient,
    root_headers: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Проверка согласованности: если в /balances есть item 'Аккумулятор 140' и site_id=1,
    то /balances/by-site тоже должен его содержать."""
    # Получаем site_id из фикстуры (не обязательно 1)
    seed = await _seed_fixture(session_factory)
    site_id = seed["site_id"]

    # Получаем все balances
    response_all = await client.get("/api/v1/balances", headers=root_headers)
    assert response_all.status_code == 200
    all_items = response_all.json()["items"]

    # Ищем item с именем "Аккумулятор 140" и site_id = site_id
    target_item = None
    for item in all_items:
        if item.get("item_name") == "Аккумулятор 140" and item["site_id"] == site_id:
            target_item = item
            break

    # Если такого item нет в БД, пропускаем проверку согласованности
    if target_item is None:
        pytest.skip("Item 'Аккумулятор 140' not found in balances for the test site")

    # Получаем balances по site_id
    response_by_site = await client.get(
        f"/api/v1/balances/by-site?site_id={site_id}",
        headers=root_headers,
    )
    assert response_by_site.status_code == 200
    site_items = response_by_site.json()["items"]

    # Проверяем, что target_item присутствует в site_items
    found = False
    for site_item in site_items:
        if (
            site_item["item_id"] == target_item["item_id"]
            and site_item["site_id"] == target_item["site_id"]
        ):
            found = True
            break
    assert found, (
        f"Item 'Аккумулятор 140' (item_id={target_item['item_id']}, site_id={site_id}) "
        "found in /balances but missing in /balances/by-site"
    )
