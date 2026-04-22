from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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


async def _seed_root_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> User:
    """Создаёт root пользователя и активный сайт, возвращает пользователя."""
    async with session_factory() as session:
        # Создаём активный сайт, чтобы root видел хотя бы один сайт
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
            full_name="Root Smoke",
            is_active=True,
            is_root=True,
            role="root",
        )
        session.add(root_user)
        await session.commit()
        return root_user


@pytest.fixture
async def root_headers(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, str]:
    """Фикстура, возвращающая заголовки аутентификации для root пользователя."""
    root_user = await _seed_root_user(session_factory)
    return {"X-User-Token": str(root_user.user_token)}


@pytest.mark.asyncio
async def test_auth_me(
    client: AsyncClient,
    root_headers: dict[str, str],
) -> None:
    """GET /api/v1/auth/me возвращает корректные данные root пользователя."""
    response = await client.get("/api/v1/auth/me", headers=root_headers)
    assert response.status_code == 200
    data = response.json()
    assert "user" in data
    user = data["user"]
    assert user["is_root"] is True
    assert user["role"] == "root"
    assert user["is_active"] is True
    # Проверяем, что user_token не возвращается в user payload
    assert "user_token" not in user
    # Проверяем, что device может быть None (root не привязан к устройству)
    assert data.get("device") is None


@pytest.mark.asyncio
async def test_auth_context(
    client: AsyncClient,
    root_headers: dict[str, str],
) -> None:
    """GET /api/v1/auth/context возвращает контекст root пользователя."""
    response = await client.get("/api/v1/auth/context", headers=root_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "root"
    assert data["is_root"] is True
    assert "available_sites" in data
    assert "permissions_summary" in data
    # Проверяем, что available_sites не пуст (должны быть все активные сайты)
    assert isinstance(data["available_sites"], list)
    assert len(data["available_sites"]) > 0, "Root должен видеть хотя бы один активный сайт"
    # Проверяем, что каждый сайт имеет необходимые поля
    for site in data["available_sites"]:
        assert "site_id" in site
        assert "code" in site
        assert "name" in site
        assert "is_active" in site
        assert "permissions" in site
        perms = site["permissions"]
        assert perms["can_view"] is True
        assert perms["can_operate"] is True
        assert perms["can_manage_catalog"] is True


@pytest.mark.asyncio
async def test_auth_sites(
    client: AsyncClient,
    root_headers: dict[str, str],
) -> None:
    """GET /api/v1/auth/sites возвращает список сайтов для root пользователя."""
    response = await client.get("/api/v1/auth/sites", headers=root_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["is_root"] is True
    assert "available_sites" in data
    assert isinstance(data["available_sites"], list)
    # Поскольку мы создали активный сайт в _seed_root_user, список должен быть не пуст
    assert len(data["available_sites"]) > 0, "Root должен видеть хотя бы один активный сайт"
    for site in data["available_sites"]:
        assert "site_id" in site
        assert "code" in site
        assert "name" in site
        assert "is_active" in site
        assert "permissions" in site
        perms = site["permissions"]
        assert perms["can_view"] is True
        assert perms["can_operate"] is True
        assert perms["can_manage_catalog"] is True


@pytest.mark.asyncio
async def test_available_sites_consistency(
    client: AsyncClient,
    root_headers: dict[str, str],
) -> None:
    """Проверяет согласованность available_sites между /auth/context и /auth/sites."""
    # Получаем контекст
    context_response = await client.get("/api/v1/auth/context", headers=root_headers)
    assert context_response.status_code == 200
    context_data = context_response.json()
    context_sites = context_data["available_sites"]
    context_site_ids = {site["site_id"] for site in context_sites}

    # Получаем список сайтов
    sites_response = await client.get("/api/v1/auth/sites", headers=root_headers)
    assert sites_response.status_code == 200
    sites_data = sites_response.json()
    sites_sites = sites_data["available_sites"]
    sites_site_ids = {site["site_id"] for site in sites_sites}

    # Проверяем, что набор site_id одинаков
    assert context_site_ids == sites_site_ids

    # Проверяем, что каждый сайт имеет одинаковые permissions (все True для root)
    for context_site in context_sites:
        site_id = context_site["site_id"]
        # Находим соответствующий сайт в ответе /sites
        matching_site = next(s for s in sites_sites if s["site_id"] == site_id)
        assert matching_site is not None
        assert context_site["permissions"] == matching_site["permissions"]