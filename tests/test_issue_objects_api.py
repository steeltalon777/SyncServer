from __future__ import annotations

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


async def _seed_fixture(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"SITE-{suffix}", name=f"Site {suffix}")
        session.add(site)
        await session.flush()

        storekeeper = User(
            username=f"sk-{suffix}",
            email=f"sk-{suffix}@example.com",
            full_name="Storekeeper",
            is_active=True,
            is_root=False,
            role="storekeeper",
            default_site_id=site.id,
        )
        chief = User(
            username=f"chief-{suffix}",
            email=f"chief-{suffix}@example.com",
            full_name="Chief",
            is_active=True,
            is_root=False,
            role="chief_storekeeper",
            default_site_id=site.id,
        )
        root = User(
            username=f"root-{suffix}",
            email=f"root-{suffix}@example.com",
            full_name="Root",
            is_active=True,
            is_root=True,
            role="storekeeper",
            default_site_id=None,
        )
        session.add_all([storekeeper, chief, root])
        await session.commit()

        return {
            "storekeeper_token": str(storekeeper.user_token),
            "chief_token": str(chief.user_token),
            "root_token": str(root.user_token),
        }


@pytest.mark.asyncio
async def test_create_issue_object(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    response = await client.post(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"display_name": "Иван Иванов", "object_type": "person"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["display_name"] == "Иван Иванов"
    assert data["object_type"] == "person"
    assert data["is_active"] is True
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_create_duplicate_issue_object(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    response = await client.post(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"display_name": "Duplicate Name", "object_type": "person"},
    )
    assert response.status_code == 200

    response2 = await client.post(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"display_name": "Duplicate Name", "object_type": "person"},
    )
    # Should return 200 since get_or_create returns existing
    assert response2.status_code == 200


@pytest.mark.asyncio
async def test_get_issue_object_by_id(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    create = await client.post(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"display_name": "Test Person", "object_type": "person"},
    )
    created_id = create.json()["id"]

    get = await client.get(
        f"/api/v1/issue-objects/{created_id}",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )
    assert get.status_code == 200
    assert get.json()["display_name"] == "Test Person"


@pytest.mark.asyncio
async def test_update_issue_object(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    create = await client.post(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"display_name": "Old Name", "object_type": "person"},
    )
    created_id = create.json()["id"]

    update = await client.patch(
        f"/api/v1/issue-objects/{created_id}",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"display_name": "New Name"},
    )
    assert update.status_code == 200
    assert update.json()["display_name"] == "New Name"


@pytest.mark.asyncio
async def test_soft_delete_issue_object(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    create = await client.post(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"display_name": "To Delete", "object_type": "person"},
    )
    created_id = create.json()["id"]

    deactivate = await client.patch(
        f"/api/v1/issue-objects/{created_id}",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"is_active": False},
    )
    assert deactivate.status_code == 200

    delete_resp = await client.delete(
        f"/api/v1/issue-objects/{created_id}",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_cannot_delete_active_issue_object(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    create = await client.post(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"display_name": "Active Object", "object_type": "person"},
    )
    created_id = create.json()["id"]

    delete_resp = await client.delete(
        f"/api/v1/issue-objects/{created_id}",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )
    assert delete_resp.status_code == 409


@pytest.mark.asyncio
async def test_list_issue_objects(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    await client.post(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"display_name": "Alpha", "object_type": "person"},
    )
    await client.post(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"display_name": "Beta", "object_type": "department"},
    )

    list_resp = await client.get(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total_count"] >= 2
    assert len(data["items"]) >= 2


@pytest.mark.asyncio
async def test_search_issue_objects(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    await client.post(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"display_name": "SpecialName", "object_type": "person"},
    )

    list_resp = await client.get(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
        params={"search": "Special"},
    )
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total_count"] >= 1


@pytest.mark.asyncio
async def test_filter_by_object_type(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    await client.post(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"display_name": "Vehicle One", "object_type": "vehicle"},
    )

    list_resp = await client.get(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
        params={"object_type": "vehicle"},
    )
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total_count"] >= 1
    for item in data["items"]:
        assert item["object_type"] == "vehicle"


@pytest.mark.asyncio
async def test_merge_issue_objects(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    source = await client.post(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"display_name": "Source Object", "object_type": "person"},
    )
    source_id = source.json()["id"]

    target = await client.post(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"display_name": "Target Object", "object_type": "person"},
    )
    target_id = target.json()["id"]

    merge_resp = await client.post(
        "/api/v1/issue-objects/merge",
        headers={"X-User-Token": seed["root_token"]},
        json={"source_id": source_id, "target_id": target_id},
    )
    assert merge_resp.status_code == 200


@pytest.mark.asyncio
async def test_merge_self_fails(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    obj = await client.post(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"display_name": "Self Merge", "object_type": "person"},
    )
    obj_id = obj.json()["id"]

    merge_resp = await client.post(
        "/api/v1/issue-objects/merge",
        headers={"X-User-Token": seed["root_token"]},
        json={"source_id": obj_id, "target_id": obj_id},
    )
    assert merge_resp.status_code == 422


@pytest.mark.asyncio
async def test_observer_can_read_issue_objects(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"SITE-{suffix}", name=f"Site {suffix}")
        session.add(site)
        await session.flush()
        observer = User(
            username=f"obs-{suffix}",
            email=f"obs-{suffix}@example.com",
            full_name="Observer",
            is_active=True,
            is_root=False,
            role="observer",
            default_site_id=site.id,
        )
        session.add(observer)
        await session.commit()
        token = str(observer.user_token)

    list_resp = await client.get(
        "/api/v1/issue-objects",
        headers={"X-User-Token": token},
    )
    assert list_resp.status_code == 200

    create_resp = await client.post(
        "/api/v1/issue-objects",
        headers={"X-User-Token": token},
        json={"display_name": "Should Fail", "object_type": "person"},
    )
    assert create_resp.status_code == 403
