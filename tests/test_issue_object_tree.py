from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.issue_object import IssueObject
from app.models.issue_object_category import IssueObjectCategory
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
        session.add(storekeeper)
        await session.commit()

        return {
            "storekeeper_token": str(storekeeper.user_token),
        }


@pytest.mark.asyncio
async def test_tree_empty(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    response = await client.get(
        "/api/v1/issue-objects/tree",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_tree_with_categories(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    parent = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Root Category"},
    )
    parent_id = parent.json()["id"]

    child = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Child Category", "parent_id": parent_id},
    )
    child_id = child.json()["id"]

    response = await client.get(
        "/api/v1/issue-objects/tree",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )
    assert response.status_code == 200
    data = response.json()

    root_nodes = [n for n in data if n["type"] == "category"]
    assert any(n["id"] == parent_id for n in root_nodes)

    parent_node = next(n for n in root_nodes if n["id"] == parent_id)
    assert len(parent_node["children"]) >= 1
    assert any(c["id"] == child_id for c in parent_node["children"])


@pytest.mark.asyncio
async def test_tree_with_objects(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    cat = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Category With Objects"},
    )
    cat_id = cat.json()["id"]

    await client.post(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"display_name": "Test Object", "object_type": "person", "category_id": cat_id},
    )

    response = await client.get(
        "/api/v1/issue-objects/tree",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )
    assert response.status_code == 200
    data = response.json()

    cat_node = next((n for n in data if n["type"] == "category" and n["id"] == cat_id), None)
    assert cat_node is not None
    assert len(cat_node["children"]) >= 1
    obj_node = next((c for c in cat_node["children"] if c["type"] == "object"), None)
    assert obj_node is not None
    assert obj_node["name"] == "Test Object"


@pytest.mark.asyncio
async def test_tree_with_search(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    cat_a = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Alpha Category"},
    )
    cat_a_id = cat_a.json()["id"]

    cat_b = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Beta Category"},
    )
    cat_b_id = cat_b.json()["id"]

    await client.post(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"display_name": "Alpha Object", "object_type": "person", "category_id": cat_a_id},
    )
    await client.post(
        "/api/v1/issue-objects",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"display_name": "Beta Object", "object_type": "person", "category_id": cat_b_id},
    )

    response = await client.get(
        "/api/v1/issue-objects/tree",
        headers={"X-User-Token": seed["storekeeper_token"]},
        params={"search": "Alpha"},
    )
    assert response.status_code == 200
    data = response.json()

    cat_names = [n["name"] for n in data]
    assert "Alpha Category" in cat_names
    assert "Beta Category" not in cat_names

    alpha_node = next(n for n in data if n["id"] == cat_a_id)
    assert any(c["type"] == "object" and c["name"] == "Alpha Object" for c in alpha_node["children"])


@pytest.mark.asyncio
async def test_tree_with_include_inactive(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    active_cat = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Active Category"},
    )
    active_cat_id = active_cat.json()["id"]

    inactive_cat = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Inactive Category", "is_active": False},
    )
    inactive_cat_id = inactive_cat.json()["id"]

    response = await client.get(
        "/api/v1/issue-objects/tree",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )
    assert response.status_code == 200
    data = response.json()
    cat_ids = [n["id"] for n in data]
    assert active_cat_id in cat_ids
    assert inactive_cat_id not in cat_ids

    response = await client.get(
        "/api/v1/issue-objects/tree",
        headers={"X-User-Token": seed["storekeeper_token"]},
        params={"include_inactive": True},
    )
    assert response.status_code == 200
    data = response.json()
    cat_ids = [n["id"] for n in data]
    assert active_cat_id in cat_ids
    assert inactive_cat_id in cat_ids


@pytest.mark.asyncio
async def test_tree_with_include_deleted(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    cat = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "To Delete"},
    )
    cat_id = cat.json()["id"]

    await client.patch(
        f"/api/v1/issue-object-categories/{cat_id}",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"is_active": False},
    )
    delete = await client.delete(
        f"/api/v1/issue-object-categories/{cat_id}",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )
    assert delete.status_code == 204

    response = await client.get(
        "/api/v1/issue-objects/tree",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert all(n["id"] != cat_id for n in data)

    response = await client.get(
        "/api/v1/issue-objects/tree",
        headers={"X-User-Token": seed["storekeeper_token"]},
        params={"include_deleted": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert any(n["id"] == cat_id for n in data)

