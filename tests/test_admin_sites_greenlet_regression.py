from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_db
from app.models.site import Site
from app.models.user import User
from main import create_app

app = create_app(enable_startup_migrations=False)

ADMIN_PREFIX = "/api/v1/admin"


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


@pytest.fixture
async def root_user(session_factory: async_sessionmaker[AsyncSession]) -> User:
    async with session_factory() as session:
        user = User(
            username=f"root-{uuid4().hex[:6]}",
            email="root@greenlet.test",
            full_name="Root Greenlet Test",
            is_active=True,
            is_root=True,
            role="root",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def seeded_site(session_factory: async_sessionmaker[AsyncSession]) -> Site:
    async with session_factory() as session:
        site = Site(
            code=f"S-GL-{uuid4().hex[:6]}",
            name="Greenlet Regression Site",
            description="Temporary site for greenlet regression test",
            is_active=True,
        )
        session.add(site)
        await session.commit()
        await session.refresh(site)
        return site


@pytest.mark.asyncio
async def test_post_site_returns_200_with_timestamps(
    client: AsyncClient,
    root_user: User,
) -> None:
    """POST /api/v1/admin/sites must return 200 with created_at and updated_at.

    This is a guard test: even before the fix, POST should work because
    SQLAlchemy 2.0 uses implicit INSERT..RETURNING for server defaults.
    """
    payload = {
        "code": f"S-GL-{uuid4().hex[:6]}",
        "name": "Greenlet POST Guard",
    }
    resp = await client.post(
        f"{ADMIN_PREFIX}/sites",
        headers={"X-User-Token": str(root_user.user_token)},
        json=payload,
    )
    assert resp.status_code == 200, f"POST returned {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body.get("created_at") is not None, "created_at must be populated"
    assert body.get("updated_at") is not None, "updated_at must be populated"
    assert body["code"] == payload["code"]
    assert body["name"] == payload["name"]


@pytest.mark.asyncio
async def test_patch_site_returns_200_with_updated_at(
    client: AsyncClient,
    root_user: User,
    seeded_site: Site,
) -> None:
    """PATCH /api/v1/admin/sites/{id} must return 200 with valid updated_at.

    Before the fix this test is RED: flush() without refresh() causes
    MissingGreenlet when SiteResponse.model_validate accesses updated_at
    outside the greenlet context.
    """
    resp = await client.patch(
        f"{ADMIN_PREFIX}/sites/{seeded_site.id}",
        headers={"X-User-Token": str(root_user.user_token)},
        json={"name": "Updated Greenlet Site"},
    )
    assert resp.status_code == 200, f"PATCH returned {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["name"] == "Updated Greenlet Site"
    assert body.get("updated_at") is not None, "updated_at must be populated after PATCH"
