from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.category import Category
from app.models.item import Item
from app.models.site import Site
from app.models.unit import Unit
from app.models.user import User
from app.models.user_access_scope import UserAccessScope
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


async def _seed_two_users(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    """Seed two storekeeper users on the same site plus catalog data needed for RECEIVE."""
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"SITE-{suffix}", name=f"Idempotency Site {suffix}")
        session.add(site)
        await session.flush()

        user_a = User(
            username=f"user-a-{suffix}",
            email=f"user-a-{suffix}@example.com",
            full_name="User A",
            is_active=True,
            is_root=False,
            role="storekeeper",
            default_site_id=site.id,
        )
        user_b = User(
            username=f"user-b-{suffix}",
            email=f"user-b-{suffix}@example.com",
            full_name="User B",
            is_active=True,
            is_root=False,
            role="storekeeper",
            default_site_id=site.id,
        )
        session.add_all([user_a, user_b])
        await session.flush()

        session.add_all(
            [
                UserAccessScope(
                    user_id=user_a.id,
                    site_id=site.id,
                    can_view=True,
                    can_operate=True,
                    can_manage_catalog=False,
                    is_active=True,
                ),
                UserAccessScope(
                    user_id=user_b.id,
                    site_id=site.id,
                    can_view=True,
                    can_operate=True,
                    can_manage_catalog=False,
                    is_active=True,
                ),
            ]
        )

        unit = Unit(code=f"U-{suffix}", name=f"Unit {suffix}", symbol=f"u{suffix[:3]}", is_active=True)
        session.add(unit)
        await session.flush()

        category = Category(
            code=f"CAT-{suffix}",
            name=f"Category {suffix}",
            normalized_name=f"category {suffix}",
            is_active=True,
        )
        session.add(category)
        await session.flush()

        item = Item(
            sku=f"SKU-{suffix}",
            name=f"Item {suffix}",
            normalized_name=f"item {suffix}",
            category_id=category.id,
            unit_id=unit.id,
            hashtags=[f"tag-{suffix}"],
            is_active=True,
        )
        session.add(item)
        await session.commit()

        return {
            "site_id": site.id,
            "item_id": item.id,
            "user_a_token": str(user_a.user_token),
            "user_b_token": str(user_b.user_token),
        }


def _create_payload(seed: dict[str, object], client_request_id: str, qty: int = 5) -> dict[str, object]:
    return {
        "operation_type": "RECEIVE",
        "site_id": seed["site_id"],
        "notes": "idempotency test",
        "client_request_id": client_request_id,
        "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": qty}],
    }


@pytest.mark.asyncio
async def test_repeat_same_key_same_payload_returns_existing(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_two_users(session_factory)
    key = f"idem-{uuid4().hex}"
    payload = _create_payload(seed, client_request_id=key, qty=5)
    headers = {"X-User-Token": seed["user_a_token"]}

    first = await client.post("/api/v1/operations", headers=headers, json=payload)
    assert first.status_code in (200, 201)
    first_body = first.json()
    first_id = first_body["id"]

    second = await client.post("/api/v1/operations", headers=headers, json=payload)
    assert second.status_code in (200, 201)
    second_body = second.json()
    assert second_body["id"] == first_id


@pytest.mark.asyncio
async def test_repeat_same_key_different_payload_returns_409(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_two_users(session_factory)
    key = f"idem-{uuid4().hex}"
    headers = {"X-User-Token": seed["user_a_token"]}

    first = await client.post(
        "/api/v1/operations",
        headers=headers,
        json=_create_payload(seed, client_request_id=key, qty=5),
    )
    assert first.status_code in (200, 201)
    first_id = first.json()["id"]

    second = await client.post(
        "/api/v1/operations",
        headers=headers,
        json=_create_payload(seed, client_request_id=key, qty=10),
    )
    assert second.status_code == 409
    detail = second.json().get("detail")
    assert detail is not None
    if isinstance(detail, dict):
        assert detail.get("code") == "idempotency_payload_conflict"
    else:
        assert "idempotency_payload_conflict" in str(detail)

    # Original operation should remain in place
    lookup = await client.get(
        "/api/v1/operations",
        headers=headers,
        params={"client_request_id": key},
    )
    assert lookup.status_code == 200
    items = lookup.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == first_id


@pytest.mark.asyncio
async def test_lookup_by_client_request_id_finds_operation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_two_users(session_factory)
    key = f"idem-{uuid4().hex}"
    headers = {"X-User-Token": seed["user_a_token"]}

    create_response = await client.post(
        "/api/v1/operations",
        headers=headers,
        json=_create_payload(seed, client_request_id=key, qty=7),
    )
    assert create_response.status_code in (200, 201)
    created_id = create_response.json()["id"]

    lookup = await client.get(
        "/api/v1/operations",
        headers=headers,
        params={"client_request_id": key},
    )
    assert lookup.status_code == 200
    body = lookup.json()
    assert body["total_count"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == created_id


@pytest.mark.asyncio
async def test_lookup_by_client_request_id_not_found(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_two_users(session_factory)
    headers = {"X-User-Token": seed["user_a_token"]}

    lookup = await client.get(
        "/api/v1/operations",
        headers=headers,
        params={"client_request_id": "nonexistent-uuid-" + uuid4().hex},
    )
    assert lookup.status_code == 200
    body = lookup.json()
    assert body["items"] == []
    assert body["total_count"] == 0


@pytest.mark.asyncio
async def test_lookup_by_client_request_id_scoped_to_user(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_two_users(session_factory)
    key = f"idem-{uuid4().hex}"

    create_response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["user_a_token"]},
        json=_create_payload(seed, client_request_id=key, qty=4),
    )
    assert create_response.status_code in (200, 201)

    # User B looks up the same key — must see nothing (per-user scoping).
    lookup_b = await client.get(
        "/api/v1/operations",
        headers={"X-User-Token": seed["user_b_token"]},
        params={"client_request_id": key},
    )
    assert lookup_b.status_code == 200
    body_b = lookup_b.json()
    assert body_b["items"] == []
    assert body_b["total_count"] == 0

    # User A still sees their own operation.
    lookup_a = await client.get(
        "/api/v1/operations",
        headers={"X-User-Token": seed["user_a_token"]},
        params={"client_request_id": key},
    )
    assert lookup_a.status_code == 200
    body_a = lookup_a.json()
    assert body_a["total_count"] == 1
    assert body_a["items"][0]["id"] == create_response.json()["id"]


@pytest.mark.asyncio
async def test_idempotency_scoped_to_user(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_two_users(session_factory)
    key = f"idem-{uuid4().hex}"
    payload = _create_payload(seed, client_request_id=key, qty=3)

    response_a = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["user_a_token"]},
        json=payload,
    )
    assert response_a.status_code in (200, 201)
    id_a = response_a.json()["id"]

    # Same key from user B must create a separate operation (idempotency is
    # scoped to created_by_user_id per contract §6.1.1).
    response_b = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["user_b_token"]},
        json=payload,
    )
    assert response_b.status_code in (200, 201)
    id_b = response_b.json()["id"]

    assert id_a != id_b

    # Each user can find their own operation via the lookup endpoint.
    lookup_a = await client.get(
        "/api/v1/operations",
        headers={"X-User-Token": seed["user_a_token"]},
        params={"client_request_id": key},
    )
    assert lookup_a.status_code == 200
    body_a = lookup_a.json()
    assert body_a["total_count"] == 1
    assert body_a["items"][0]["id"] == id_a

    lookup_b = await client.get(
        "/api/v1/operations",
        headers={"X-User-Token": seed["user_b_token"]},
        params={"client_request_id": key},
    )
    assert lookup_b.status_code == 200
    body_b = lookup_b.json()
    assert body_b["total_count"] == 1
    assert body_b["items"][0]["id"] == id_b
