from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.site import Site
from app.repos.events_repo import EventsRepo
from app.schemas.sync import EventIn, EventPayload, PushRequest
from app.services.event_ingest import EventIngestService
from app.services.sync_service import SyncService
from app.services.uow import UnitOfWork


async def _seed_site_device(session: AsyncSession) -> tuple[Site, Device]:
    site = Site(code=f"S-{uuid4().hex[:6]}", name="Test Site")
    session.add(site)
    await session.flush()

    device = Device(
        site_id=site.id,
        device_code=f"device-{uuid4().hex[:8]}",
        device_name="Test Device",
        device_token=uuid4(),
    )
    session.add(device)
    await session.flush()
    return site, device


@pytest.mark.asyncio
async def test_db_smoke(db_session: AsyncSession) -> None:
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar_one() == 1


@pytest.mark.asyncio
async def test_insert_event_returns_server_seq(db_session: AsyncSession) -> None:
    site, device = await _seed_site_device(db_session)
    service = EventIngestService(EventsRepo(db_session))

    event_in = EventIn(
        event_uuid=uuid4(),
        event_type="sale",
        event_datetime=datetime.now(UTC),
        payload=EventPayload(lines=[]),
    )

    result = await service.process_event(site_id=site.id, device_id=device.id, event_in=event_in)

    assert result.status == "accepted"
    assert isinstance(result.server_seq, int)
    assert (result.server_seq or 0) > 0


@pytest.mark.asyncio
async def test_duplicate_same_payload(db_session: AsyncSession) -> None:
    site, device = await _seed_site_device(db_session)
    service = EventIngestService(EventsRepo(db_session))
    event_uuid = uuid4()

    event_in = EventIn(
        event_uuid=event_uuid,
        event_type="sale",
        event_datetime=datetime.now(UTC),
        payload=EventPayload(doc_id="D1", lines=[]),
    )

    first = await service.process_event(site_id=site.id, device_id=device.id, event_in=event_in)
    second = await service.process_event(site_id=site.id, device_id=device.id, event_in=event_in)

    assert first.status == "accepted"
    assert second.status == "duplicate_same_payload"
    assert second.server_seq == first.server_seq


@pytest.mark.asyncio
async def test_uuid_collision(db_session: AsyncSession) -> None:
    site, device = await _seed_site_device(db_session)
    service = EventIngestService(EventsRepo(db_session))
    event_uuid = uuid4()

    first = EventIn(
        event_uuid=event_uuid,
        event_type="sale",
        event_datetime=datetime.now(UTC),
        payload=EventPayload(doc_id="A", lines=[]),
    )
    second = EventIn(
        event_uuid=event_uuid,
        event_type="sale",
        event_datetime=datetime.now(UTC),
        payload=EventPayload(doc_id="B", lines=[]),
    )

    await service.process_event(site_id=site.id, device_id=device.id, event_in=first)
    collision = await service.process_event(site_id=site.id, device_id=device.id, event_in=second)

    assert collision.status == "uuid_collision"
    assert collision.reason_code == "uuid_collision"


@pytest.mark.asyncio
async def test_pull_since_seq_sorted(db_session: AsyncSession) -> None:
    events_repo = EventsRepo(db_session)
    service = EventIngestService(events_repo)

    site_1, device_1 = await _seed_site_device(db_session)
    site_2, device_2 = await _seed_site_device(db_session)

    first = await service.process_event(
        site_id=site_1.id,
        device_id=device_1.id,
        event_in=EventIn(
            event_uuid=uuid4(),
            event_type="sale",
            event_datetime=datetime.now(UTC),
            payload=EventPayload(doc_id="1", lines=[]),
        ),
    )
    second = await service.process_event(
        site_id=site_1.id,
        device_id=device_1.id,
        event_in=EventIn(
            event_uuid=uuid4(),
            event_type="sale",
            event_datetime=datetime.now(UTC),
            payload=EventPayload(doc_id="2", lines=[]),
        ),
    )

    await service.process_event(
        site_id=site_2.id,
        device_id=device_2.id,
        event_in=EventIn(
            event_uuid=uuid4(),
            event_type="sale",
            event_datetime=datetime.now(UTC),
            payload=EventPayload(doc_id="3", lines=[]),
        ),
    )

    pulled = await events_repo.pull(site_id=site_1.id, since_seq=first.server_seq or 0, limit=100)

    assert len(pulled) == 1
    assert pulled[0].server_seq == second.server_seq
    assert pulled[0].site_id == site_1.id


@pytest.mark.asyncio
async def test_sync_service_push_classification(db_session: AsyncSession) -> None:
    site, device = await _seed_site_device(db_session)
    sync_service = SyncService()

    request = PushRequest(
        site_id=site.id,
        device_id=device.id,
        batch_id=uuid4(),
        events=[
            EventIn(
                event_uuid=uuid4(),
                event_type="sale",
                event_datetime=datetime.now(UTC),
                payload=EventPayload(doc_id="A", lines=[]),
            )
        ],
    )

    async with UnitOfWork(db_session) as uow:
        first = await sync_service.process_push(uow, request)

    async with UnitOfWork(db_session) as uow:
        second = await sync_service.process_push(uow, request)

    assert len(first.accepted) == 1
    assert len(second.duplicates) == 1
    assert second.duplicates[0].server_seq == first.accepted[0].server_seq
