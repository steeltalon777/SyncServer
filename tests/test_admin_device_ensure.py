from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.site import Site
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


async def _seed_root_and_sites(session_factory: async_sessionmaker[AsyncSession]):
    async with session_factory() as session:
        site = Site(code=f"S-{uuid4().hex[:6]}", name="Primary Site")
        root_user = User(
            username=f"root-{uuid4().hex[:6]}",
            email="root@example.com",
            full_name="Root User",
            is_active=True,
            is_root=True,
            role="root",
        )
        session.add_all([site, root_user])
        await session.commit()
        await session.refresh(site)
        await session.refresh(root_user)
        return root_user, site


@pytest.mark.asyncio
async def test_ensure_creates_new_device(client, session_factory):
    """PUT by-code creates a new device when code is not found."""
    root_user, site = await _seed_root_and_sites(session_factory)

    response = await client.put(
        "/api/v1/admin/devices/by-code/test-device-001",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"device_name": "Test Device", "site_id": site.id, "is_active": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["device_code"] == "test-device-001"
    assert body["device_name"] == "Test Device"
    assert body["device_token"] is not None


@pytest.mark.asyncio
async def test_ensure_returns_same_id_and_token(client, session_factory):
    """Two identical PUT requests -> one device, same device_id and token."""
    root_user, site = await _seed_root_and_sites(session_factory)

    first = await client.put(
        "/api/v1/admin/devices/by-code/dup-device",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"device_name": "Dup Device", "site_id": site.id, "is_active": True},
    )
    assert first.status_code == 200
    first_body = first.json()

    second = await client.put(
        "/api/v1/admin/devices/by-code/dup-device",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"device_name": "Dup Device", "site_id": site.id, "is_active": True},
    )
    assert second.status_code == 200
    second_body = second.json()

    assert first_body["device_id"] == second_body["device_id"]
    assert first_body["device_token"] == second_body["device_token"]


@pytest.mark.asyncio
async def test_ensure_updates_existing_device(client, session_factory):
    """PUT by-code updates existing device fields but keeps token."""
    root_user, site = await _seed_root_and_sites(session_factory)

    create_resp = await client.put(
        "/api/v1/admin/devices/by-code/updatable-device",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"device_name": "Original Name", "site_id": site.id, "is_active": True},
    )
    original = create_resp.json()

    update_resp = await client.put(
        "/api/v1/admin/devices/by-code/updatable-device",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"device_name": "Updated Name", "site_id": None, "is_active": False},
    )
    updated = update_resp.json()

    assert updated["device_id"] == original["device_id"]
    assert updated["device_token"] == original["device_token"]
    assert updated["device_name"] == "Updated Name"
    assert updated["site_id"] is None
    assert updated["is_active"] is False


@pytest.mark.asyncio
async def test_ensure_requires_root(client, session_factory):
    """Non-root roles get 403 on ensure endpoint."""
    async with session_factory() as session:
        observer = User(
            username=f"obs-{uuid4().hex[:6]}",
            is_active=True,
            is_root=False,
            role="observer",
        )
        session.add(observer)
        await session.commit()
        await session.refresh(observer)
        obs_token = observer.user_token

    response = await client.put(
        "/api/v1/admin/devices/by-code/no-access",
        headers={"X-User-Token": str(obs_token)},
        json={"device_name": "No Access", "is_active": True},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_ensure_route_precedence(client, session_factory):
    """by-code route must not be caught by {device_id} route."""
    root_user, site = await _seed_root_and_sites(session_factory)

    response = await client.put(
        "/api/v1/admin/devices/by-code/unique-route-test",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"device_name": "Route Test", "site_id": site.id, "is_active": True},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_ensure_invalid_site_returns_404(client, session_factory):
    """Non-existent site_id -> 404."""
    root_user, _ = await _seed_root_and_sites(session_factory)

    response = await client.put(
        "/api/v1/admin/devices/by-code/bad-site-device",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"device_name": "Bad Site Device", "site_id": 99999, "is_active": True},
    )
    assert response.status_code == 404
