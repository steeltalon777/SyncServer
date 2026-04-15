from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.category import Category
from app.models.device import Device
from app.models.item import Item
from app.models.site import Site
from app.models.unit import Unit
from app.models.user import User
from main import create_app

app = create_app(enable_startup_migrations=False)


async def _seed_site_and_device(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[Site, Device]:
    async with session_factory() as session:
        site = Site(code=f"S-{uuid4().hex[:6]}", name="HTTP Test Site")
        session.add(site)
        await session.flush()

        device = Device(
            site_id=site.id,
            device_code=f"device-{uuid4().hex[:8]}",
            device_name="HTTP Device",
            device_token=uuid4(),
        )
        session.add(device)
        await session.commit()
        return site, device


async def _seed_root_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> User:
    async with session_factory() as session:
        root_user = User(
            username=f"root-{uuid4().hex[:6]}",
            email=f"root-{uuid4().hex[:6]}@example.com",
            full_name="HTTP Root",
            is_active=True,
            is_root=True,
            role="root",
        )
        session.add(root_user)
        await session.commit()
        return root_user


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
async def test_ping_auth_ok(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    site, device = await _seed_site_and_device(session_factory)

    response = await client.post(
        "/api/v1/ping",
        json={
            "site_id": site.id,
            "device_id": device.id,
            "last_server_seq": 0,
            "outbox_count": 3,
            "client_time": datetime.now(UTC).isoformat(),
        },
        headers={"X-Device-Token": str(device.device_token)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["server_seq_upto"] == 0
    assert body["backoff_seconds"] == 0


@pytest.mark.asyncio
async def test_ping_auth_ok_with_placeholder_device_id(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    site, device = await _seed_site_and_device(session_factory)

    response = await client.post(
        "/api/v1/ping",
        json={
            "site_id": site.id,
            "device_id": 0,
            "last_server_seq": 0,
            "outbox_count": 1,
            "client_time": datetime.now(UTC).isoformat(),
        },
        headers={"X-Device-Token": str(device.device_token)},
    )

    assert response.status_code == 200
    assert response.json()["backoff_seconds"] == 0


@pytest.mark.asyncio
async def test_push_accept_duplicate_collision(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    site, device = await _seed_site_and_device(session_factory)
    collision_uuid = uuid4()

    response = await client.post(
        "/api/v1/push",
        json={
            "site_id": site.id,
            "device_id": device.id,
            "batch_id": str(uuid4()),
            "events": [
                {
                    "event_uuid": str(collision_uuid),
                    "event_type": "sale",
                    "event_datetime": datetime.now(UTC).isoformat(),
                    "schema_version": 1,
                    "payload": {"doc_id": "A", "lines": []},
                },
                {
                    "event_uuid": str(collision_uuid),
                    "event_type": "sale",
                    "event_datetime": datetime.now(UTC).isoformat(),
                    "schema_version": 1,
                    "payload": {"doc_id": "A", "lines": []},
                },
                {
                    "event_uuid": str(collision_uuid),
                    "event_type": "sale",
                    "event_datetime": datetime.now(UTC).isoformat(),
                    "schema_version": 1,
                    "payload": {"doc_id": "B", "lines": []},
                },
            ],
        },
        headers={"X-Device-Token": str(device.device_token)},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["accepted"]) == 1
    assert len(body["duplicates"]) == 1
    assert len(body["rejected"]) == 1
    assert body["rejected"][0]["reason_code"] == "uuid_collision"


@pytest.mark.asyncio
async def test_pull_ordering(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    site, device = await _seed_site_and_device(session_factory)

    push_response = await client.post(
        "/api/v1/push",
        json={
            "site_id": site.id,
            "device_id": device.id,
            "batch_id": str(uuid4()),
            "events": [
                {
                    "event_uuid": str(uuid4()),
                    "event_type": "sale",
                    "event_datetime": datetime.now(UTC).isoformat(),
                    "schema_version": 1,
                    "payload": {"doc_id": "first", "lines": []},
                },
                {
                    "event_uuid": str(uuid4()),
                    "event_type": "sale",
                    "event_datetime": datetime.now(UTC).isoformat(),
                    "schema_version": 1,
                    "payload": {"doc_id": "second", "lines": []},
                },
            ],
        },
        headers={"X-Device-Token": str(device.device_token)},
    )
    assert push_response.status_code == 200

    accepted = push_response.json()["accepted"]
    first_seq = accepted[0]["server_seq"]

    pull_response = await client.post(
        "/api/v1/pull",
        json={
            "site_id": site.id,
            "device_id": device.id,
            "since_seq": first_seq,
            "limit": 100,
        },
        headers={"X-Device-Token": str(device.device_token)},
    )

    assert pull_response.status_code == 200
    pull_body = pull_response.json()
    assert len(pull_body["events"]) == 1
    assert pull_body["events"][0]["server_seq"] > first_seq
    assert pull_body["next_since_seq"] == pull_body["events"][0]["server_seq"]


@pytest.mark.asyncio
async def test_catalog_items_incremental(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    root_user = await _seed_root_user(session_factory)

    base_time = datetime.now(UTC) - timedelta(days=1)
    async with session_factory() as session:
        category = Category(name="All", updated_at=base_time)
        unit = Unit(name="Piece", symbol="pcs", updated_at=base_time)
        session.add_all([category, unit])
        await session.flush()

        item_1 = Item(name="Milk", unit_id=unit.id, category_id=category.id, updated_at=base_time)
        item_2 = Item(
            name="Bread",
            unit_id=unit.id,
            category_id=category.id,
            updated_at=base_time + timedelta(minutes=1),
        )
        session.add_all([item_1, item_2])
        await session.commit()

    headers = {"X-User-Token": str(root_user.user_token)}

    first_response = await client.get(
        "/api/v1/catalog/items",
        params={"updated_after": (base_time - timedelta(minutes=1)).isoformat(), "limit": 100},
        headers=headers,
    )
    assert first_response.status_code == 200
    first_body = first_response.json()
    assert len(first_body["items"]) == 2
    assert first_body["next_updated_after"] is not None

    second_response = await client.get(
        "/api/v1/catalog/items",
        params={"updated_after": first_body["next_updated_after"], "limit": 100},
        headers=headers,
    )
    assert second_response.status_code == 200
    assert second_response.json()["items"] == []


@pytest.mark.asyncio
async def test_auth_fail_bad_token(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    site, device = await _seed_site_and_device(session_factory)

    response = await client.post(
        "/api/v1/ping",
        json={
            "site_id": site.id,
            "device_id": device.id,
            "last_server_seq": 0,
            "outbox_count": 0,
        },
        headers={"X-Device-Token": str(uuid4())},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid X-Device-Token"


@pytest.mark.asyncio
async def test_auth_fail_invalid_token_format(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    site, device = await _seed_site_and_device(session_factory)

    response = await client.post(
        "/api/v1/ping",
        json={
            "site_id": site.id,
            "device_id": -1,
            "last_server_seq": 0,
            "outbox_count": 0,
        },
        headers={"X-Device-Token": "not-a-uuid"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid X-Device-Token"


@pytest.mark.asyncio
async def test_catalog_admin_write_flow(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    root_user = await _seed_root_user(session_factory)
    headers = {"X-User-Token": str(root_user.user_token)}

    create_unit = await client.post("/api/v1/catalog/admin/units", json={"name": "Box", "symbol": "box"}, headers=headers)
    assert create_unit.status_code == 200
    unit_id = create_unit.json()["id"]

    create_category = await client.post("/api/v1/catalog/admin/categories", json={"name": "Food"}, headers=headers)
    assert create_category.status_code == 200
    category_id = create_category.json()["id"]

    create_item = await client.post(
        "/api/v1/catalog/admin/items",
        json={"name": "Sugar", "sku": "SUGAR-001", "category_id": category_id, "unit_id": unit_id},
        headers=headers,
    )
    assert create_item.status_code == 200
    item_id = create_item.json()["id"]

    deactivate_item = await client.patch(
        f"/api/v1/catalog/admin/items/{item_id}",
        json={"is_active": False},
        headers=headers,
    )
    assert deactivate_item.status_code == 200
    assert deactivate_item.json()["is_active"] is False


@pytest.mark.asyncio
async def test_catalog_admin_category_cycle_validation(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    root_user = await _seed_root_user(session_factory)
    headers = {"X-User-Token": str(root_user.user_token)}

    root_resp = await client.post("/api/v1/catalog/admin/categories", json={"name": "Root"}, headers=headers)
    assert root_resp.status_code == 200
    root_id = root_resp.json()["id"]

    child_resp = await client.post(
        "/api/v1/catalog/admin/categories",
        json={"name": "Child", "parent_id": root_id},
        headers=headers,
    )
    assert child_resp.status_code == 200
    child_id = child_resp.json()["id"]

    cycle_resp = await client.patch(
        f"/api/v1/catalog/admin/categories/{root_id}",
        json={"parent_id": child_id},
        headers=headers,
    )
    assert cycle_resp.status_code == 400
    assert cycle_resp.json()["detail"] == "category cycle detected"
