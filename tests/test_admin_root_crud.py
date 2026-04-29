"""
Тесты Root-only CRUD для users, devices, sites на SyncServer.

Проверяют:
- Root может выполнять CRUD для users / devices / sites.
- Non-root (chief_storekeeper, observer) не может выполнять CRUD.
- Новые site get / delete работают корректно.
"""

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


async def _seed(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[User, User, Site, Site]:
    """Create root user, chief_storekeeper user, and two sites."""
    async with session_factory() as session:
        site_a = Site(code=f"S-{uuid4().hex[:6]}", name="Site A")
        site_b = Site(code=f"S-{uuid4().hex[:6]}", name="Site B")
        root_user = User(
            username=f"root-{uuid4().hex[:6]}",
            email="root@test.com",
            full_name="Root User",
            is_active=True,
            is_root=True,
            role="root",
        )
        chief_user = User(
            username=f"chief-{uuid4().hex[:6]}",
            email="chief@test.com",
            full_name="Chief Storekeeper",
            is_active=True,
            is_root=False,
            role="chief_storekeeper",
        )
        session.add_all([site_a, site_b, root_user, chief_user])
        await session.commit()
        await session.refresh(site_a)
        await session.refresh(site_b)
        await session.refresh(root_user)
        await session.refresh(chief_user)
        return root_user, chief_user, site_a, site_b


# ---------------------------------------------------------------------------
# Users CRUD – Root-only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_root_can_list_users(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, _, _, _ = await _seed(session_factory)
    resp = await client.get(
        "/api/v1/admin/users",
        headers={"X-User-Token": str(root_user.user_token)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "users" in data
    assert data["total_count"] >= 1


@pytest.mark.asyncio
async def test_non_root_cannot_list_users(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, chief_user, _, _ = await _seed(session_factory)
    resp = await client.get(
        "/api/v1/admin/users",
        headers={"X-User-Token": str(chief_user.user_token)},
    )
    assert resp.status_code == 403
    assert "root permissions required" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_root_can_get_user(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, chief_user, _, _ = await _seed(session_factory)
    resp = await client.get(
        f"/api/v1/admin/users/{chief_user.id}",
        headers={"X-User-Token": str(root_user.user_token)},
    )
    assert resp.status_code == 200
    assert resp.json()["username"] == chief_user.username


@pytest.mark.asyncio
async def test_non_root_cannot_get_user(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, chief_user, _, _ = await _seed(session_factory)
    resp = await client.get(
        f"/api/v1/admin/users/{root_user.id}",
        headers={"X-User-Token": str(chief_user.user_token)},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_root_can_create_user(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, _, site_a, _ = await _seed(session_factory)
    resp = await client.post(
        "/api/v1/admin/users",
        headers={"X-User-Token": str(root_user.user_token)},
        json={
            "username": f"newuser-{uuid4().hex[:6]}",
            "email": "new@test.com",
            "full_name": "New User",
            "is_active": True,
            "is_root": False,
            "role": "storekeeper",
            "default_site_id": site_a.id,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["username"].startswith("newuser-")


@pytest.mark.asyncio
async def test_non_root_cannot_create_user(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, chief_user, site_a, _ = await _seed(session_factory)
    resp = await client.post(
        "/api/v1/admin/users",
        headers={"X-User-Token": str(chief_user.user_token)},
        json={
            "username": f"newuser-{uuid4().hex[:6]}",
            "email": "new@test.com",
            "full_name": "New User",
            "is_active": True,
            "is_root": False,
            "role": "storekeeper",
            "default_site_id": site_a.id,
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_root_can_update_user(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, chief_user, _, _ = await _seed(session_factory)
    resp = await client.patch(
        f"/api/v1/admin/users/{chief_user.id}",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"full_name": "Updated Chief"},
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Updated Chief"


@pytest.mark.asyncio
async def test_non_root_cannot_update_user(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, chief_user, _, _ = await _seed(session_factory)
    resp = await client.patch(
        f"/api/v1/admin/users/{root_user.id}",
        headers={"X-User-Token": str(chief_user.user_token)},
        json={"full_name": "Hacked"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_root_can_delete_user(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, chief_user, _, _ = await _seed(session_factory)
    resp = await client.delete(
        f"/api/v1/admin/users/{chief_user.id}",
        headers={"X-User-Token": str(root_user.user_token)},
    )
    assert resp.status_code == 200
    # soft delete — is_active becomes False
    assert resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_non_root_cannot_delete_user(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, chief_user, _, _ = await _seed(session_factory)
    resp = await client.delete(
        f"/api/v1/admin/users/{root_user.id}",
        headers={"X-User-Token": str(chief_user.user_token)},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Devices CRUD – Root-only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_root_can_list_devices(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, _, site_a, _ = await _seed(session_factory)
    # create a device first
    await client.post(
        "/api/v1/admin/devices",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"device_code": "dev-1", "device_name": "Device 1", "site_id": site_a.id, "is_active": True},
    )
    resp = await client.get(
        "/api/v1/admin/devices",
        headers={"X-User-Token": str(root_user.user_token)},
    )
    assert resp.status_code == 200
    assert resp.json()["total_count"] >= 1


@pytest.mark.asyncio
async def test_non_root_cannot_list_devices(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, chief_user, site_a, _ = await _seed(session_factory)
    # create a device as root
    await client.post(
        "/api/v1/admin/devices",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"device_code": "dev-1", "device_name": "Device 1", "site_id": site_a.id, "is_active": True},
    )
    resp = await client.get(
        "/api/v1/admin/devices",
        headers={"X-User-Token": str(chief_user.user_token)},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_root_can_get_device(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, _, site_a, _ = await _seed(session_factory)
    create_resp = await client.post(
        "/api/v1/admin/devices",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"device_code": "dev-get", "device_name": "Get Test", "site_id": site_a.id, "is_active": True},
    )
    device_id = create_resp.json()["device_id"]
    resp = await client.get(
        f"/api/v1/admin/devices/{device_id}",
        headers={"X-User-Token": str(root_user.user_token)},
    )
    assert resp.status_code == 200
    assert resp.json()["device_code"] == "dev-get"


@pytest.mark.asyncio
async def test_non_root_cannot_get_device(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, chief_user, site_a, _ = await _seed(session_factory)
    create_resp = await client.post(
        "/api/v1/admin/devices",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"device_code": "dev-get2", "device_name": "Get Test", "site_id": site_a.id, "is_active": True},
    )
    device_id = create_resp.json()["device_id"]
    resp = await client.get(
        f"/api/v1/admin/devices/{device_id}",
        headers={"X-User-Token": str(chief_user.user_token)},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_root_can_create_device(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, _, site_a, _ = await _seed(session_factory)
    resp = await client.post(
        "/api/v1/admin/devices",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"device_code": "new-dev", "device_name": "New Device", "site_id": site_a.id, "is_active": True},
    )
    assert resp.status_code == 200
    assert resp.json()["device_code"] == "new-dev"


@pytest.mark.asyncio
async def test_non_root_cannot_create_device(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, chief_user, site_a, _ = await _seed(session_factory)
    resp = await client.post(
        "/api/v1/admin/devices",
        headers={"X-User-Token": str(chief_user.user_token)},
        json={"device_code": "new-dev", "device_name": "New Device", "site_id": site_a.id, "is_active": True},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_root_can_update_device(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, _, site_a, _ = await _seed(session_factory)
    create_resp = await client.post(
        "/api/v1/admin/devices",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"device_code": "upd-dev", "device_name": "Before", "site_id": site_a.id, "is_active": True},
    )
    device_id = create_resp.json()["device_id"]
    resp = await client.patch(
        f"/api/v1/admin/devices/{device_id}",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"device_name": "After"},
    )
    assert resp.status_code == 200
    assert resp.json()["device_name"] == "After"


@pytest.mark.asyncio
async def test_non_root_cannot_update_device(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, chief_user, site_a, _ = await _seed(session_factory)
    create_resp = await client.post(
        "/api/v1/admin/devices",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"device_code": "upd-dev2", "device_name": "Before", "site_id": site_a.id, "is_active": True},
    )
    device_id = create_resp.json()["device_id"]
    resp = await client.patch(
        f"/api/v1/admin/devices/{device_id}",
        headers={"X-User-Token": str(chief_user.user_token)},
        json={"device_name": "Hacked"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_root_can_delete_device(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, _, site_a, _ = await _seed(session_factory)
    create_resp = await client.post(
        "/api/v1/admin/devices",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"device_code": "del-dev", "device_name": "Delete Me", "site_id": site_a.id, "is_active": True},
    )
    device_id = create_resp.json()["device_id"]
    resp = await client.delete(
        f"/api/v1/admin/devices/{device_id}",
        headers={"X-User-Token": str(root_user.user_token)},
    )
    assert resp.status_code == 200
    # soft delete — is_active becomes False
    assert resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_non_root_cannot_delete_device(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, chief_user, site_a, _ = await _seed(session_factory)
    create_resp = await client.post(
        "/api/v1/admin/devices",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"device_code": "del-dev2", "device_name": "Delete Me", "site_id": site_a.id, "is_active": True},
    )
    device_id = create_resp.json()["device_id"]
    resp = await client.delete(
        f"/api/v1/admin/devices/{device_id}",
        headers={"X-User-Token": str(chief_user.user_token)},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Sites CRUD – Root-only (including new get/delete)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_root_can_list_sites(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, _, _, _ = await _seed(session_factory)
    resp = await client.get(
        "/api/v1/admin/sites",
        headers={"X-User-Token": str(root_user.user_token)},
    )
    assert resp.status_code == 200
    assert resp.json()["total_count"] >= 2


@pytest.mark.asyncio
async def test_non_root_cannot_list_sites(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, chief_user, _, _ = await _seed(session_factory)
    resp = await client.get(
        "/api/v1/admin/sites",
        headers={"X-User-Token": str(chief_user.user_token)},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_root_can_get_site(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, _, site_a, _ = await _seed(session_factory)
    resp = await client.get(
        f"/api/v1/admin/sites/{site_a.id}",
        headers={"X-User-Token": str(root_user.user_token)},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Site A"


@pytest.mark.asyncio
async def test_non_root_cannot_get_site(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, chief_user, site_a, _ = await _seed(session_factory)
    resp = await client.get(
        f"/api/v1/admin/sites/{site_a.id}",
        headers={"X-User-Token": str(chief_user.user_token)},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_root_can_create_site(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, _, _, _ = await _seed(session_factory)
    resp = await client.post(
        "/api/v1/admin/sites",
        headers={"X-User-Token": str(root_user.user_token)},
        json={
            "code": f"NEW-{uuid4().hex[:6]}",
            "name": "New Site",
            "is_active": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Site"


@pytest.mark.asyncio
async def test_non_root_cannot_create_site(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, chief_user, _, _ = await _seed(session_factory)
    resp = await client.post(
        "/api/v1/admin/sites",
        headers={"X-User-Token": str(chief_user.user_token)},
        json={
            "code": f"NEW-{uuid4().hex[:6]}",
            "name": "New Site",
            "is_active": True,
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_root_can_update_site(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, _, site_a, _ = await _seed(session_factory)
    resp = await client.patch(
        f"/api/v1/admin/sites/{site_a.id}",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"name": "Updated Site A"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Site A"


@pytest.mark.asyncio
async def test_non_root_cannot_update_site(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, chief_user, site_a, _ = await _seed(session_factory)
    resp = await client.patch(
        f"/api/v1/admin/sites/{site_a.id}",
        headers={"X-User-Token": str(chief_user.user_token)},
        json={"name": "Hacked Site"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_root_can_delete_site(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, _, site_a, _ = await _seed(session_factory)
    resp = await client.delete(
        f"/api/v1/admin/sites/{site_a.id}",
        headers={"X-User-Token": str(root_user.user_token)},
    )
    assert resp.status_code == 200
    # soft delete — is_active becomes False
    assert resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_non_root_cannot_delete_site(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, chief_user, site_a, _ = await _seed(session_factory)
    resp = await client.delete(
        f"/api/v1/admin/sites/{site_a.id}",
        headers={"X-User-Token": str(chief_user.user_token)},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_site_returns_404_for_nonexistent(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, _, _, _ = await _seed(session_factory)
    resp = await client.get(
        "/api/v1/admin/sites/999999",
        headers={"X-User-Token": str(root_user.user_token)},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_site_returns_404_for_nonexistent(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, _, _, _ = await _seed(session_factory)
    resp = await client.delete(
        "/api/v1/admin/sites/999999",
        headers={"X-User-Token": str(root_user.user_token)},
    )
    assert resp.status_code == 404
