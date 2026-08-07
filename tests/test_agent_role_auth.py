"""Agent role (ADR-0030) — auth/sites/context/admin tests.

Covers TZ-AGENT-ROLE-SYNCSERVER §4.3 / §10.1 / §10.7:
- GET /auth/sites returns all active sites with can_operate=false,
  can_manage_catalog=true;
- GET /auth/context returns the agent permissions summary even without a
  default site;
- /auth/me returns role=agent;
- agent has no /admin/* authority.
"""
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

EXPECTED_AGENT_SUMMARY = {
    "can_read_operations": True,
    "can_create_operations": True,
    "can_read_balances": True,
    "can_manage_catalog": True,
    "can_manage_root_admin": False,
    "is_root": False,
}


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


async def _seed(session_factory: async_sessionmaker[AsyncSession], *, sites_count: int = 2) -> dict[str, object]:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        sites = [
            Site(code=f"SITE-{suffix}-{i}", name=f"Site {suffix} {i}", is_active=True)
            for i in range(sites_count)
        ]
        session.add_all(sites)
        await session.flush()

        inactive_site = Site(code=f"SITE-{suffix}-off", name=f"Offline Site {suffix}", is_active=False)
        session.add(inactive_site)
        await session.flush()

        agent_user = User(
            username=f"agent-{suffix}", email=f"agent-{suffix}@example.com",
            full_name="Agent", is_active=True, is_root=False,
            role="agent", default_site_id=None,
        )
        observer_user = User(
            username=f"observer-{suffix}", email=f"observer-{suffix}@example.com",
            full_name="Observer", is_active=True, is_root=False,
            role="observer", default_site_id=None,
        )
        session.add_all([agent_user, observer_user])
        await session.flush()

        if sites:
            session.add(
                UserAccessScope(
                    user_id=observer_user.id,
                    site_id=sites[0].id,
                    can_view=True,
                    can_operate=False,
                    can_manage_catalog=False,
                    is_active=True,
                )
            )
        await session.commit()

        return {
            "active_site_ids": [site.id for site in sites],
            "inactive_site_id": inactive_site.id,
            "agent_token": str(agent_user.user_token),
            "observer_token": str(observer_user.user_token),
        }


@pytest.mark.asyncio
async def test_agent_auth_sites_returns_all_active_sites(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)

    response = await client.get(
        "/api/v1/auth/sites",
        headers={"X-User-Token": seed["agent_token"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_root"] is False

    available = body["available_sites"]
    assert len(available) == 2
    returned_ids = {site["site_id"] for site in available}
    assert returned_ids == set(seed["active_site_ids"])
    assert seed["inactive_site_id"] not in returned_ids

    for site in available:
        assert site["permissions"] == {
            "can_view": True,
            "can_operate": False,
            "can_manage_catalog": True,
        }


@pytest.mark.asyncio
async def test_agent_auth_context_permissions_summary(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)

    response = await client.get(
        "/api/v1/auth/context",
        headers={"X-User-Token": seed["agent_token"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["role"] == "agent"
    assert body["is_root"] is False
    assert body["permissions_summary"] == EXPECTED_AGENT_SUMMARY

    available = body["available_sites"]
    assert len(available) == 2
    assert {site["site_id"] for site in available} == set(seed["active_site_ids"])
    for site in available:
        assert site["permissions"]["can_operate"] is False
        assert site["permissions"]["can_manage_catalog"] is True


@pytest.mark.asyncio
async def test_agent_auth_context_summary_without_sites(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Even with zero sites / no default site the agent summary stays
    agent-typical (ADR-0030 §4.3)."""
    seed = await _seed(session_factory, sites_count=0)

    response = await client.get(
        "/api/v1/auth/context",
        headers={"X-User-Token": seed["agent_token"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["default_site"] is None
    assert body["available_sites"] == []
    assert body["permissions_summary"] == EXPECTED_AGENT_SUMMARY


@pytest.mark.asyncio
async def test_agent_auth_me_returns_role_agent(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)

    response = await client.get(
        "/api/v1/auth/me",
        headers={"X-User-Token": seed["agent_token"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["role"] == "agent"
    assert body["user"]["is_root"] is False


@pytest.mark.asyncio
async def test_agent_has_no_admin_access(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed(session_factory)

    users = await client.get(
        "/api/v1/admin/users",
        headers={"X-User-Token": seed["agent_token"]},
    )
    assert users.status_code == 403

    roles = await client.get(
        "/api/v1/admin/roles",
        headers={"X-User-Token": seed["agent_token"]},
    )
    assert roles.status_code == 403


@pytest.mark.asyncio
async def test_regression_observer_sites_scope_based(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Observer still sees only scoped sites with scope permissions."""
    seed = await _seed(session_factory)

    response = await client.get(
        "/api/v1/auth/sites",
        headers={"X-User-Token": seed["observer_token"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    available = body["available_sites"]
    assert len(available) == 1
    assert available[0]["site_id"] == seed["active_site_ids"][0]
    assert available[0]["permissions"] == {
        "can_view": True,
        "can_operate": False,
        "can_manage_catalog": False,
    }
