"""Tests for per-device sync_state tracking (ADR-0016)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.models.device import Device
from app.models.site import Site
from app.services.uow import UnitOfWork
from httpx import ASGITransport, AsyncClient
from main import create_app
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

app = create_app(enable_startup_migrations=False)


async def _seed_site_and_device(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[Site, Device]:
    async with session_factory() as session:
        site = Site(code=f"S-{uuid4().hex[:6]}", name="SyncState Test Site")
        session.add(site)
        await session.flush()

        device = Device(
            site_id=site.id,
            device_code=f"device-{uuid4().hex[:8]}",
            device_name="SyncState Device",
            device_token=uuid4(),
        )
        session.add(device)
        await session.commit()
        return site, device


async def _seed_root_user(
    session_factory: async_sessionmaker[AsyncSession],
):
    from app.models.user import User

    async with session_factory() as session:
        root = User(
            username=f"root-{uuid4().hex[:6]}",
            email=f"root-{uuid4().hex[:6]}@example.com",
            full_name="SyncState Root",
            is_active=True,
            is_root=True,
            role="root",
        )
        session.add(root)
        await session.commit()
        return root


# ---------------------------------------------------------------------------
# Unit tests: SyncStateRepo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_state_repo_upsert_creates(
    uow: UnitOfWork,
):
    """First upsert creates a row and persists provided values."""
    site = Site(code=f"S-{uuid4().hex[:6]}", name="Repo Test Site 1")
    uow.session.add(site)
    await uow.session.flush()
    device = Device(
        site_id=site.id,
        device_code=f"device-{uuid4().hex[:8]}",
        device_name="Repo Device 1",
        device_token=uuid4(),
    )
    uow.session.add(device)
    await uow.session.flush()

    state = await uow.sync_state.upsert(
        device_id=device.id,
        last_sequence_number=42,
        status="online",
        last_error=None,
    )
    await uow.session.commit()

    fetched = await uow.sync_state.get_by_device_id(device.id)
    assert fetched is not None
    assert fetched.device_id == device.id
    assert fetched.last_sequence_number == 42
    assert fetched.status == "online"
    assert fetched.last_error is None
    assert fetched.last_sync_at is not None
    assert state.device_id == device.id


@pytest.mark.asyncio
async def test_sync_state_repo_upsert_updates_existing(
    uow: UnitOfWork,
):
    site = Site(code=f"S-{uuid4().hex[:6]}", name="Repo Test Site 2")
    uow.session.add(site)
    await uow.session.flush()
    device = Device(
        site_id=site.id,
        device_code=f"device-{uuid4().hex[:8]}",
        device_name="Repo Device 2",
        device_token=uuid4(),
    )
    uow.session.add(device)
    await uow.session.flush()

    await uow.sync_state.upsert(
        device_id=device.id,
        last_sequence_number=10,
        status="online",
    )
    await uow.session.commit()

    state2 = await uow.sync_state.upsert(
        device_id=device.id,
        last_sequence_number=20,
        status="online",
    )
    await uow.session.commit()

    fetched = await uow.sync_state.get_by_device_id(device.id)
    assert fetched is not None
    assert fetched.last_sequence_number == 20
    assert state2.last_sequence_number == 20


@pytest.mark.asyncio
async def test_sync_state_repo_get_by_device_id_none(
    uow: UnitOfWork,
):
    fetched = await uow.sync_state.get_by_device_id(999_999)
    assert fetched is None


@pytest.mark.asyncio
async def test_sync_state_repo_monotonic_invariant(
    uow: UnitOfWork,
):
    """Higher incoming last_sequence_number wins; lower is rejected."""
    site = Site(code=f"S-{uuid4().hex[:6]}", name="Monotonic Site")
    uow.session.add(site)
    await uow.session.flush()
    device = Device(
        site_id=site.id,
        device_code=f"device-{uuid4().hex[:8]}",
        device_name="Monotonic Device",
        device_token=uuid4(),
    )
    uow.session.add(device)
    await uow.session.flush()

    await uow.sync_state.upsert(
        device_id=device.id,
        last_sequence_number=100,
        status="online",
    )
    await uow.session.commit()

    # Lower sequence number must not regress the cursor.
    await uow.sync_state.upsert(
        device_id=device.id,
        last_sequence_number=50,
        status="online",
    )
    await uow.session.commit()

    fetched = await uow.sync_state.get_by_device_id(device.id)
    assert fetched is not None
    assert fetched.last_sequence_number == 100  # unchanged


# ---------------------------------------------------------------------------
# HTTP integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def http_client(db_session: AsyncSession):
    from app.core.db import get_db

    async def override_get_db():
        async with db_session.bind.connect() as _:
            yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_ping_creates_sync_state(
    db_session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
):
    from app.core.db import get_db

    site, device = await _seed_site_and_device(session_factory)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/api/v1/ping",
                json={
                    "site_id": site.id,
                    "device_id": device.id,
                    "last_server_seq": 0,
                    "outbox_count": 0,
                },
                headers={"X-Device-Token": str(device.device_token)},
            )
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()

    # Verify sync_state row was created.
    from app.services.uow import UnitOfWork

    uow = UnitOfWork(db_session)
    state = await uow.sync_state.get_by_device_id(device.id)
    assert state is not None
    assert state.status == "online"
    assert state.last_sync_at is not None


@pytest.mark.asyncio
async def test_pull_updates_sync_state(
    db_session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
):
    from app.core.db import get_db
    from app.services.uow import UnitOfWork

    site, device = await _seed_site_and_device(session_factory)

    # Pre-push an event to have something to pull.
    async with session_factory() as s:
        from app.services.uow import UnitOfWork
        from app.models.event import Event
        from app.schemas.sync import EventPayload
        import json, hashlib

        payload = {"doc_id": "X", "lines": []}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        ev = Event(
            event_uuid=uuid4(),
            site_id=site.id,
            device_id=device.id,
            event_type="sale",
            event_datetime=datetime.now(UTC),
            schema_version=1,
            payload=payload,
            payload_hash=hashlib.sha256(canonical.encode()).hexdigest(),
        )
        s.add(ev)
        await s.commit()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/api/v1/pull",
                json={
                    "site_id": site.id,
                    "device_id": device.id,
                    "since_seq": 0,
                    "limit": 100,
                },
                headers={"X-Device-Token": str(device.device_token)},
            )
        assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()

    uow = UnitOfWork(db_session)
    state = await uow.sync_state.get_by_device_id(device.id)
    assert state is not None
    assert state.last_sequence_number >= 1


@pytest.mark.asyncio
async def test_get_sync_status_own_device(
    db_session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
):
    from app.core.db import get_db
    from app.services.uow import UnitOfWork

    site, device = await _seed_site_and_device(session_factory)

    # Pre-seed sync_state for the device.
    uow = UnitOfWork(db_session)
    await uow.sync_state.upsert(
        device_id=device.id,
        last_sequence_number=15,
        status="online",
    )
    await db_session.commit()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/sync/status/{device.id}",
                headers={"X-Device-Token": str(device.device_token)},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["device_id"] == device.id
        assert body["last_sequence_number"] == 15
        assert body["status"] == "online"
        assert "behind_by" in body
        assert "server_seq_upto" in body
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_sync_status_other_device_forbidden(
    db_session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
):
    from app.core.db import get_db

    site, device_a = await _seed_site_and_device(session_factory)
    # second device on same site
    async with session_factory() as s:
        device_b = Device(
            site_id=site.id,
            device_code=f"device-{uuid4().hex[:8]}",
            device_name="Device B",
            device_token=uuid4(),
        )
        s.add(device_b)
        await s.commit()
        device_b_id = device_b.id

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            # device A requests sync/status of device B
            response = await c.get(
                f"/api/v1/sync/status/{device_b_id}",
                headers={"X-Device-Token": str(device_a.device_token)},
            )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_sync_status_root_user_any_device(
    db_session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
):
    from app.core.db import get_db

    site, device = await _seed_site_and_device(session_factory)
    root = await _seed_root_user(session_factory)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/sync/status/{device.id}",
                headers={"X-User-Token": str(root.user_token)},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["device_id"] == device.id
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_sync_status_unknown_device_returns_zeroed(
    db_session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
):
    from app.core.db import get_db

    site, device = await _seed_site_and_device(session_factory)

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/sync/status/{device.id}",
                headers={"X-Device-Token": str(device.device_token)},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["device_id"] == device.id
        assert body["last_sequence_number"] == 0
        assert body["status"] == "unknown"
        assert body["last_sync_at"] is None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_push_records_error_on_collision(
    db_session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
):
    """Push that produces a uuid_collision sets status='error' and last_error."""
    from app.core.db import get_db
    from app.services.uow import UnitOfWork

    site, device = await _seed_site_and_device(session_factory)
    collision_uuid = str(uuid4())

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/api/v1/push",
                json={
                    "site_id": site.id,
                    "device_id": device.id,
                    "batch_id": str(uuid4()),
                    "events": [
                        {
                            "event_uuid": collision_uuid,
                            "event_type": "sale",
                            "event_datetime": datetime.now(UTC).isoformat(),
                            "schema_version": 1,
                            "payload": {"doc_id": "A", "lines": []},
                        },
                        {
                            "event_uuid": collision_uuid,
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
        assert len(body["rejected"]) == 1
        assert body["rejected"][0]["reason_code"] == "uuid_collision"
    finally:
        app.dependency_overrides.clear()

    uow = UnitOfWork(db_session)
    state = await uow.sync_state.get_by_device_id(device.id)
    assert state is not None
    assert state.status == "error"
    assert state.last_error is not None
    assert "conflict" in state.last_error.lower()
