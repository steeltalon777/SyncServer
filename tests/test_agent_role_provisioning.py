"""Agent role (ADR-0030) — provisioning and role enumeration tests.

Covers TZ-AGENT-ROLE-SYNCSERVER §10.1:
- root POST /auth/sync-user can create/update role=agent;
- root POST /admin/users can create role=agent;
- GET /admin/roles (authorized admin) contains 'agent';
- agent itself still gets 403 on /admin/roles;
- /auth/me returns role=agent.
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


async def _seed_root(session_factory: async_sessionmaker[AsyncSession]) -> User:
    async with session_factory() as session:
        root_user = User(
            username=f"root-{uuid4().hex[:6]}",
            email="root@example.com",
            full_name="Root User",
            is_active=True,
            is_root=True,
            role="root",
        )
        session.add(root_user)
        await session.commit()
        await session.refresh(root_user)
        return root_user


@pytest.mark.asyncio
async def test_admin_roles_contains_agent_for_root(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """TZ §10.1 / §2.6: authorized admin sees the fifth canonical role."""
    root_user = await _seed_root(session_factory)
    response = await client.get(
        "/api/v1/admin/roles",
        headers={"X-User-Token": str(root_user.user_token)},
    )
    assert response.status_code == 200
    assert "agent" in response.json()


@pytest.mark.asyncio
async def test_admin_roles_contains_agent_for_chief(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """TZ §10.1: chief_storekeeper (admin_basic) also enumerates 'agent'."""
    async with session_factory() as session:
        chief = User(
            username=f"chief-{uuid4().hex[:6]}",
            email="chief@example.com",
            full_name="Chief",
            is_active=True,
            is_root=False,
            role="chief_storekeeper",
        )
        session.add(chief)
        await session.commit()
        await session.refresh(chief)
    response = await client.get(
        "/api/v1/admin/roles",
        headers={"X-User-Token": str(chief.user_token)},
    )
    assert response.status_code == 200
    assert "agent" in response.json()


@pytest.mark.asyncio
async def test_agent_cannot_call_admin_roles(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """TZ §10.1: agent itself gets 403 on /admin/roles (sees role via /auth/me)."""
    async with session_factory() as session:
        agent_user = User(
            username=f"agent-{uuid4().hex[:6]}",
            email="agent@example.com",
            full_name="Agent",
            is_active=True,
            is_root=False,
            role="agent",
        )
        session.add(agent_user)
        await session.commit()
        await session.refresh(agent_user)
    response = await client.get(
        "/api/v1/admin/roles",
        headers={"X-User-Token": str(agent_user.user_token)},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_root_sync_user_creates_agent(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """TZ §10.1: existing root-only /auth/sync-user flow provisions role=agent."""
    root_user = await _seed_root(session_factory)
    user_id = uuid4()

    create_response = await client.post(
        "/api/v1/auth/sync-user",
        headers={"X-User-Token": str(root_user.user_token)},
        json={
            "id": str(user_id),
            "username": "llm-agent-1",
            "email": "agent@example.com",
            "full_name": "LLM Agent",
            "is_active": True,
            "is_root": False,
            "role": "agent",
            "default_site_id": None,
        },
    )

    assert create_response.status_code == 200
    body = create_response.json()
    assert body["status"] == "created"
    assert body["user"]["role"] == "agent"
    assert body["user"]["is_root"] is False
    assert body["user"]["user_token"]

    # agent token from the provisioning flow authenticates as role=agent.
    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"X-User-Token": body["user"]["user_token"]},
    )
    assert me_response.status_code == 200
    assert me_response.json()["user"]["role"] == "agent"


@pytest.mark.asyncio
async def test_root_admin_users_create_agent(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """TZ §10.1: root admin user-create flow provisions role=agent."""
    root_user = await _seed_root(session_factory)

    create_response = await client.post(
        "/api/v1/admin/users",
        headers={"X-User-Token": str(root_user.user_token)},
        json={
            "username": "llm-agent-2",
            "email": "agent2@example.com",
            "full_name": "LLM Agent Two",
            "is_active": True,
            "is_root": False,
            "role": "agent",
        },
    )

    assert create_response.status_code == 200, create_response.text
    body = create_response.json()
    assert body["role"] == "agent"
    assert body["is_root"] is False
    assert body["id"]

    # Token is exposed to root through the sync-state endpoint; it authenticates
    # as the agent role (TZ §7.2: server issues and stores its own user_token).
    sync_state_response = await client.get(
        f"/api/v1/admin/users/{body['id']}/sync-state",
        headers={"X-User-Token": str(root_user.user_token)},
    )
    assert sync_state_response.status_code == 200
    agent_token = sync_state_response.json()["user"]["user_token"]
    assert agent_token
    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"X-User-Token": agent_token},
    )
    assert me_response.status_code == 200
    assert me_response.json()["user"]["role"] == "agent"
