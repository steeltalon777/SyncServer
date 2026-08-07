"""Agent role (ADR-0030) — balances read access tests.

Covers TZ-AGENT-ROLE-SYNCSERVER §4.2 / §10.2:
- agent reads balances globally (list / by-site / summary);
- observer read parity regression.
"""
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


async def _seed(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"SITE-{suffix}", name=f"Site {suffix}", is_active=True)
        session.add(site)
        await session.flush()

        agent_user = User(
            username=f"agent-{suffix}", email=f"agent-{suffix}@example.com",
            full_name="Agent", is_active=True, is_root=False,
            role="agent", default_site_id=site.id,
        )
        observer_user = User(
            username=f"observer-{suffix}", email=f"observer-{suffix}@example.com",
            full_name="Observer", is_active=True, is_root=False,
            role="observer", default_site_id=site.id,
        )
        session.add_all([agent_user, observer_user])
        await session.commit()

        return {
            "site_id": site.id,
            "agent_token": str(agent_user.user_token),
            "observer_token": str(observer_user.user_token),
        }


@pytest.mark.asyncio
async def test_agent_reads_balances(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)

    response = await client.get(
        "/api/v1/balances",
        headers={"X-User-Token": seed["agent_token"]},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "items" in data
    assert "total_count" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_agent_reads_balances_by_site(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)

    response = await client.get(
        f"/api/v1/balances/by-site?site_id={seed['site_id']}",
        headers={"X-User-Token": seed["agent_token"]},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    for item in data["items"]:
        assert item["site_id"] == seed["site_id"]


@pytest.mark.asyncio
async def test_agent_reads_balances_summary(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)

    response = await client.get(
        "/api/v1/balances/summary",
        headers={"X-User-Token": seed["agent_token"]},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "accessible_sites_count" in data
    assert "summary" in data


@pytest.mark.asyncio
async def test_regression_observer_reads_balances(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)

    response = await client.get(
        "/api/v1/balances",
        headers={"X-User-Token": seed["observer_token"]},
    )
    assert response.status_code == 200, response.text
