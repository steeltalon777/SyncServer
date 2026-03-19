from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.user import User
from main import app


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


@pytest.mark.asyncio
async def test_auth_me_does_not_return_user_token(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = User(
            id=uuid4(),
            username=f"user-{uuid4().hex[:6]}",
            email="user@example.com",
            full_name="Test User",
            is_active=True,
            is_root=False,
            role="observer",
            default_site_id=None,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    response = await client.get(
        "/api/v1/auth/me",
        headers={"X-User-Token": str(user.user_token)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == str(user.id)
    assert "user_token" not in body["user"]
