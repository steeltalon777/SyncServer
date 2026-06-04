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
        observer = User(
            username=f"obs-{suffix}",
            email=f"obs-{suffix}@example.com",
            full_name="Observer",
            is_active=True,
            is_root=False,
            role="observer",
            default_site_id=site.id,
        )
        session.add_all([storekeeper, observer])
        await session.commit()

        return {
            "storekeeper_token": str(storekeeper.user_token),
            "observer_token": str(observer.user_token),
        }


async def _ensure_category(session_factory: async_sessionmaker[AsyncSession], category_id: int) -> None:
    """Ensure a category exists in the test schema."""
    from app.models.issue_object_category import IssueObjectCategory
    async with session_factory() as session:
        cat = await session.get(IssueObjectCategory, category_id)
        if cat is not None:
            return
        cat = IssueObjectCategory(id=category_id, name=f"Test Cat {category_id}", normalized_key=f"test_cat_{category_id}", sort_order=0, is_active=True)
        session.add(cat)
        await session.commit()


@pytest.mark.asyncio
async def test_create_category(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    response = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Тестовая категория", "sort_order": 1},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Тестовая категория"
    assert data["is_active"] is True
    assert data["id"] is not None
    assert data["parent_id"] is None


@pytest.mark.asyncio
async def test_create_duplicate_category_fails(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Unique Category", "sort_order": 1},
    )
    response = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Unique Category", "sort_order": 1},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_get_category(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    create = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Get Test Category"},
    )
    cat_id = create.json()["id"]

    get = await client.get(
        f"/api/v1/issue-object-categories/{cat_id}",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )
    assert get.status_code == 200
    assert get.json()["name"] == "Get Test Category"


@pytest.mark.asyncio
async def test_get_category_not_found(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    get = await client.get(
        "/api/v1/issue-object-categories/99999",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )
    assert get.status_code == 404


@pytest.mark.asyncio
async def test_update_category(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    create = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Old Name"},
    )
    cat_id = create.json()["id"]

    update = await client.patch(
        f"/api/v1/issue-object-categories/{cat_id}",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "New Name"},
    )
    assert update.status_code == 200
    assert update.json()["name"] == "New Name"


@pytest.mark.asyncio
async def test_update_category_nonexistent_parent_fails(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    create = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Orphan Category"},
    )
    cat_id = create.json()["id"]

    update = await client.patch(
        f"/api/v1/issue-object-categories/{cat_id}",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"parent_id": 99999},
    )
    assert update.status_code == 422


@pytest.mark.asyncio
async def test_delete_category(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    create = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Category To Delete", "is_active": True},
    )
    cat_id = create.json()["id"]

    delete = await client.delete(
        f"/api/v1/issue-object-categories/{cat_id}",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )
    assert delete.status_code == 204


@pytest.mark.asyncio
async def test_delete_category_with_children_fails(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    parent = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Parent Cat"},
    )
    parent_id = parent.json()["id"]

    await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Child Cat", "parent_id": parent_id},
    )

    delete = await client.delete(
        f"/api/v1/issue-object-categories/{parent_id}",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )
    assert delete.status_code == 409


@pytest.mark.asyncio
async def test_list_categories(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Alpha"},
    )
    await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Beta"},
    )

    response = await client.get(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] >= 2
    assert len(data["items"]) >= 2


@pytest.mark.asyncio
async def test_search_categories(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "SearchableCatName"},
    )

    response = await client.get(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        params={"search": "Searchable"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] >= 1


@pytest.mark.asyncio
async def test_observer_cannot_write_categories(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    response = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["observer_token"]},
        json={"name": "Should Fail"},
    )
    assert response.status_code == 403

    list_resp = await client.get(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["observer_token"]},
    )
    assert list_resp.status_code == 200


@pytest.mark.asyncio
async def test_create_category_with_parent(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    parent = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Parent Category"},
    )
    parent_id = parent.json()["id"]

    child = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Child Category", "parent_id": parent_id},
    )
    assert child.status_code == 200
    assert child.json()["parent_id"] == parent_id


@pytest.mark.asyncio
async def test_update_category_duplicate_name_fails(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    cat1 = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "First Category"},
    )
    cat1_id = cat1.json()["id"]

    cat2 = await client.post(
        "/api/v1/issue-object-categories",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "Second Category"},
    )
    cat2_id = cat2.json()["id"]

    update = await client.patch(
        f"/api/v1/issue-object-categories/{cat2_id}",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"name": "First Category"},
    )
    assert update.status_code == 409
