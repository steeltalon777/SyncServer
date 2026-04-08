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


async def _seed_root_and_sites(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[User, Site, Site]:
    async with session_factory() as session:
        site_1 = Site(code=f"S-{uuid4().hex[:6]}", name="Primary Site")
        site_2 = Site(code=f"S-{uuid4().hex[:6]}", name="Secondary Site")
        root_user = User(
            username=f"root-{uuid4().hex[:6]}",
            email="root@example.com",
            full_name="Root User",
            is_active=True,
            is_root=True,
            role="root",
        )
        session.add_all([site_1, site_2, root_user])
        await session.commit()
        await session.refresh(site_1)
        await session.refresh(site_2)
        await session.refresh(root_user)
        return root_user, site_1, site_2


@pytest.mark.asyncio
async def test_sync_user_returns_stable_token_and_blocks_root_payload(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, site_1, _ = await _seed_root_and_sites(session_factory)
    user_id = uuid4()

    create_response = await client.post(
        "/api/v1/auth/sync-user",
        headers={"X-User-Token": str(root_user.user_token)},
        json={
            "id": str(user_id),
            "username": "storekeeper-1",
            "email": "storekeeper@example.com",
            "full_name": "Store Keeper",
            "is_active": True,
            "is_root": False,
            "role": "storekeeper",
            "default_site_id": site_1.id,
        },
    )

    assert create_response.status_code == 200
    create_body = create_response.json()
    assert create_body["status"] == "created"
    first_token = create_body["user"]["user_token"]
    assert first_token

    update_response = await client.post(
        "/api/v1/auth/sync-user",
        headers={"X-User-Token": str(root_user.user_token)},
        json={
            "id": str(user_id),
            "username": "storekeeper-1",
            "email": "updated@example.com",
            "full_name": "Store Keeper Updated",
            "is_active": True,
            "is_root": False,
            "role": "storekeeper",
            "default_site_id": site_1.id,
        },
    )

    assert update_response.status_code == 200
    update_body = update_response.json()
    assert update_body["status"] == "updated"
    assert update_body["user"]["user_token"] == first_token

    forbidden_response = await client.post(
        "/api/v1/auth/sync-user",
        headers={"X-User-Token": str(root_user.user_token)},
        json={
            "id": str(uuid4()),
            "username": "bad-root",
            "email": "bad-root@example.com",
            "full_name": "Bad Root",
            "is_active": True,
            "is_root": True,
            "role": "root",
            "default_site_id": None,
        },
    )

    assert forbidden_response.status_code == 403
    assert forbidden_response.json()["detail"] == "sync-user cannot create or update root users"


@pytest.mark.asyncio
async def test_user_sync_state_scope_replace_and_rotate_token(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, site_1, site_2 = await _seed_root_and_sites(session_factory)
    user_id = uuid4()

    sync_response = await client.post(
        "/api/v1/auth/sync-user",
        headers={"X-User-Token": str(root_user.user_token)},
        json={
            "id": str(user_id),
            "username": "observer-1",
            "email": "observer@example.com",
            "full_name": "Observer User",
            "is_active": True,
            "is_root": False,
            "role": "observer",
            "default_site_id": site_1.id,
        },
    )
    assert sync_response.status_code == 200
    old_token = sync_response.json()["user"]["user_token"]

    scopes_response = await client.put(
        f"/api/v1/admin/users/{user_id}/scopes",
        headers={"X-User-Token": str(root_user.user_token)},
        json={
            "scopes": [
                {
                    "site_id": site_1.id,
                    "can_view": True,
                    "can_operate": False,
                    "can_manage_catalog": False,
                },
                {
                    "site_id": site_2.id,
                    "can_view": True,
                    "can_operate": False,
                    "can_manage_catalog": False,
                },
            ]
        },
    )

    assert scopes_response.status_code == 200
    scopes_body = scopes_response.json()
    assert len(scopes_body) == 2

    sync_state_response = await client.get(
        f"/api/v1/admin/users/{user_id}/sync-state",
        headers={"X-User-Token": str(root_user.user_token)},
    )

    assert sync_state_response.status_code == 200
    sync_state_body = sync_state_response.json()
    assert sync_state_body["user"]["user_token"] == old_token
    assert {scope["site_id"] for scope in sync_state_body["scopes"]} == {site_1.id, site_2.id}

    rotate_response = await client.post(
        f"/api/v1/admin/users/{user_id}/rotate-token",
        headers={"X-User-Token": str(root_user.user_token)},
    )

    assert rotate_response.status_code == 200
    rotate_body = rotate_response.json()
    assert rotate_body["user_id"] == str(user_id)
    assert rotate_body["user_token"] != old_token

    old_token_response = await client.get(
        "/api/v1/auth/me",
        headers={"X-User-Token": old_token},
    )
    assert old_token_response.status_code == 401
    assert old_token_response.json()["detail"] == "invalid X-User-Token"

    new_token_response = await client.get(
        "/api/v1/auth/me",
        headers={"X-User-Token": rotate_body["user_token"]},
    )
    assert new_token_response.status_code == 200
    assert new_token_response.json()["user"]["id"] == str(user_id)


@pytest.mark.asyncio
async def test_create_device_returns_device_token(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user, site_1, _ = await _seed_root_and_sites(session_factory)

    create_response = await client.post(
        "/api/v1/admin/devices",
        headers={"X-User-Token": str(root_user.user_token)},
        json={
            "device_code": "django-web",
            "device_name": "Django Web Client",
            "site_id": site_1.id,
            "is_active": True,
        },
    )

    assert create_response.status_code == 200
    body = create_response.json()
    assert body["device_code"] == "django-web"
    assert body["device_name"] == "Django Web Client"
    assert body["site_id"] == site_1.id
    assert body["is_active"] is True
    assert body["device_token"]
