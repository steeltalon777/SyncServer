"""Unified authentication tests for the header-based auth contract.

Covers all scenarios from the auth unification spec:
- user-only endpoints
- device-only endpoints
- combined user+device endpoints
- error cases (missing tokens, inactive users/devices, invalid tokens)
- role-based access control
"""
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.device import Device
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_user(session_factory, *, is_active=True, is_root=False, role="observer", default_site_id=None):
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            username=f"user-{uuid4().hex[:6]}",
            email=f"user-{uuid4().hex[:6]}@example.com",
            full_name="Test User",
            is_active=is_active,
            is_root=is_root,
            role=role,
            default_site_id=default_site_id,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _create_device(session_factory, *, is_active=True, site_id=None):
    async with session_factory() as session:
        device = Device(
            device_code=f"dev-{uuid4().hex[:8]}",
            device_name="Test Device",
            site_id=site_id,
            is_active=is_active,
            device_token=uuid4(),
        )
        session.add(device)
        await session.commit()
        await session.refresh(device)
        return device


# ---------------------------------------------------------------------------
# User-only endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_user_only_endpoint_valid_token(client, session_factory):
    """user-only endpoint with valid X-User-Token"""
    user = await _create_user(session_factory)
    response = await client.get(
        "/api/v1/auth/me",
        headers={"X-User-Token": str(user.user_token)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == str(user.id)


@pytest.mark.asyncio
async def test_user_only_endpoint_missing_token(client, session_factory):
    """user-only endpoint without X-User-Token → 401"""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_only_endpoint_invalid_token(client, session_factory):
    """user-only endpoint with invalid X-User-Token → 401"""
    response = await client.get(
        "/api/v1/auth/me",
        headers={"X-User-Token": str(uuid4())},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_only_endpoint_inactive_user(client, session_factory):
    """user-only endpoint with inactive user → 403"""
    user = await _create_user(session_factory, is_active=False)
    response = await client.get(
        "/api/v1/auth/me",
        headers={"X-User-Token": str(user.user_token)},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Device-only endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_device_only_endpoint_valid_token(client, session_factory):
    """device-only endpoint with valid X-Device-Token"""
    device = await _create_device(session_factory)
    response = await client.post(
        "/api/v1/ping",
        json={"device_id": device.id, "site_id": device.site_id or 0, "outbox_count": 0},
        headers={"X-Device-Token": str(device.device_token)},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_device_only_endpoint_with_device_id_zero(client, session_factory):
    """device-only endpoint with device_id=0 in body — should still auth by token"""
    device = await _create_device(session_factory)
    response = await client.post(
        "/api/v1/ping",
        json={"device_id": 0, "site_id": 0, "outbox_count": 0},
        headers={"X-Device-Token": str(device.device_token)},
    )
    # Auth succeeds by token; device_id=0 is just payload
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_device_only_endpoint_invalid_token(client, session_factory):
    """device-only endpoint with invalid X-Device-Token → 401"""
    response = await client.post(
        "/api/v1/ping",
        json={"device_id": 0, "site_id": 0, "outbox_count": 0},
        headers={"X-Device-Token": str(uuid4())},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_device_only_endpoint_missing_token(client, session_factory):
    """device-only endpoint without X-Device-Token → 401"""
    response = await client.post(
        "/api/v1/ping",
        json={"device_id": 0, "site_id": 0, "outbox_count": 0},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_device_only_endpoint_inactive_device(client, session_factory):
    """device-only endpoint with inactive device → 403"""
    device = await _create_device(session_factory, is_active=False)
    response = await client.post(
        "/api/v1/ping",
        json={"device_id": device.id, "site_id": device.site_id or 0, "outbox_count": 0},
        headers={"X-Device-Token": str(device.device_token)},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Combined token tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_both_tokens_valid(client, session_factory):
    """endpoint with both валидных tokens → full identity context"""
    user = await _create_user(session_factory)
    device = await _create_device(session_factory)
    response = await client.get(
        "/api/v1/auth/me",
        headers={
            "X-User-Token": str(user.user_token),
            "X-Device-Token": str(device.device_token),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == str(user.id)
    assert body["device"] is not None
    assert body["device"]["device_id"] == device.id


@pytest.mark.asyncio
async def test_valid_user_token_invalid_device_token(client, session_factory):
    """valid user token + invalid device token → 401"""
    user = await _create_user(session_factory)
    response = await client.get(
        "/api/v1/auth/me",
        headers={
            "X-User-Token": str(user.user_token),
            "X-Device-Token": str(uuid4()),
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_valid_device_token_invalid_user_token(client, session_factory):
    """valid device token + invalid user token → 401 (user-required endpoint)"""
    device = await _create_device(session_factory)
    response = await client.get(
        "/api/v1/auth/me",
        headers={
            "X-User-Token": str(uuid4()),
            "X-Device-Token": str(device.device_token),
        },
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Role-based access tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_root_only_endpoint_with_regular_user(client, session_factory):
    """root-only endpoint with regular user → 403"""
    user = await _create_user(session_factory, is_root=False, role="observer")
    response = await client.get(
        "/api/v1/admin/users",
        headers={"X-User-Token": str(user.user_token)},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_root_only_endpoint_with_root_user(client, session_factory):
    """root-only endpoint with root user → 200"""
    user = await _create_user(session_factory, is_root=True, role="root")
    response = await client.get(
        "/api/v1/admin/users",
        headers={"X-User-Token": str(user.user_token)},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chief_storekeeper_admin_access(client, session_factory):
    """chief_storekeeper can access admin endpoints that allow admin_basic"""
    user = await _create_user(session_factory, is_root=False, role="chief_storekeeper")
    response = await client.get(
        "/api/v1/admin/roles",
        headers={"X-User-Token": str(user.user_token)},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_storekeeper_admin_access_denied(client, session_factory):
    """storekeeper cannot access admin endpoints"""
    user = await _create_user(session_factory, is_root=False, role="storekeeper")
    response = await client.get(
        "/api/v1/admin/roles",
        headers={"X-User-Token": str(user.user_token)},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_observer_admin_access_denied(client, session_factory):
    """observer cannot access admin endpoints"""
    user = await _create_user(session_factory, is_root=False, role="observer")
    response = await client.get(
        "/api/v1/admin/roles",
        headers={"X-User-Token": str(user.user_token)},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Bootstrap sync tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bootstrap_requires_root(client, session_factory):
    """bootstrap/sync requires root user"""
    user = await _create_user(session_factory, is_root=False, role="observer")
    device = await _create_device(session_factory)
    response = await client.post(
        "/api/v1/bootstrap/sync",
        json={"device_id": 0, "site_id": 0},
        headers={
            "X-User-Token": str(user.user_token),
            "X-Device-Token": str(device.device_token),
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_bootstrap_with_root(client, session_factory):
    """bootstrap/sync with root user → 200"""
    user = await _create_user(session_factory, is_root=True, role="root")
    device = await _create_device(session_factory)
    response = await client.post(
        "/api/v1/bootstrap/sync",
        json={"device_id": 0, "site_id": 0},
        headers={
            "X-User-Token": str(user.user_token),
            "X-Device-Token": str(device.device_token),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_root"] is True
