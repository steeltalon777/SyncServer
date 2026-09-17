"""Release-blocker regression: the Operations journal period filter must use
business time (``effective_at``), not ingestion time (``created_at``).

Scenario from the 4.0 historical OCR/backfill workflow:
- operation entered in September, business date February;
- filtering the September business period must NOT return the February op;
- filtering the February business period must return it.

The API filter stays server-side (``effective_after``/``effective_before``);
the ``created_after``/``created_before`` capability remains available and is
asserted here as untouched.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.operation import Operation
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
        site = Site(code=f"EFF-FILTER-{suffix}", name=f"Effective Filter Site {suffix}")
        session.add(site)
        await session.flush()

        root_user = User(
            username=f"root-eff-filter-{suffix}",
            email=f"root-eff-filter-{suffix}@example.com",
            full_name="Root Effective Filter",
            is_active=True,
            is_root=True,
            role="root",
            default_site_id=site.id,
        )
        session.add(root_user)
        await session.commit()

        return {
            "site_id": site.id,
            "root_user_id": root_user.id,
            "root_token": str(root_user.user_token),
        }


async def _add_operation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    site_id: int,
    user_id: UUID,
    created_at: datetime,
    effective_at: datetime | None,
    operation_id: UUID | None = None,
) -> UUID:
    async with session_factory() as session:
        operation = Operation(
            id=operation_id or uuid4(),
            site_id=site_id,
            operation_type="RECEIVE",
            status="submitted",
            created_by_user_id=user_id,
            created_at=created_at,
            updated_at=created_at,
            effective_at=effective_at,
            submitted_at=created_at,
            submitted_by_user_id=user_id,
        )
        session.add(operation)
        await session.commit()
        return operation.id


async def _list_operations(
    client: AsyncClient,
    token: str,
    *,
    params: dict[str, str],
) -> dict:
    response = await client.get(
        "/api/v1/operations",
        headers={"X-User-Token": token},
        params={"page": 1, "page_size": 50, **params},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_effective_period_filter_uses_business_date_not_created_at(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A (created Sep, effective Feb) must be excluded from the September
    business period and included in the February one; B (created Sep,
    effective Sep) the other way around."""
    seed = await _seed_fixture(session_factory)

    a = await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 9, 17, 9, 0, tzinfo=UTC),
        effective_at=datetime(2026, 2, 15, 9, 0, tzinfo=UTC),
    )
    b = await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 9, 10, 9, 0, tzinfo=UTC),
        effective_at=datetime(2026, 9, 12, 9, 0, tzinfo=UTC),
    )

    september = await _list_operations(
        client,
        seed["root_token"],
        params={
            "effective_after": "2026-09-01T00:00:00Z",
            "effective_before": "2026-09-30T23:59:59Z",
        },
    )
    september_ids = [item["id"] for item in september["items"]]
    assert september_ids == [str(b)]
    assert str(a) not in september_ids
    assert september["total_count"] == 1

    february = await _list_operations(
        client,
        seed["root_token"],
        params={
            "effective_after": "2026-02-01T00:00:00Z",
            "effective_before": "2026-02-28T23:59:59Z",
        },
    )
    february_ids = [item["id"] for item in february["items"]]
    assert february_ids == [str(a)]
    assert february["total_count"] == 1


@pytest.mark.asyncio
async def test_effective_period_filter_falls_back_to_created_at_for_legacy_null(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Legacy rows without effective_at are filtered by created_at, matching
    the accepted list-order/display fallback semantics."""
    seed = await _seed_fixture(session_factory)

    legacy = await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 9, 5, 9, 0, tzinfo=UTC),
        effective_at=None,
    )
    backdated = await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 9, 20, 9, 0, tzinfo=UTC),
        effective_at=datetime(2026, 2, 15, 9, 0, tzinfo=UTC),
    )

    september = await _list_operations(
        client,
        seed["root_token"],
        params={
            "effective_after": "2026-09-01T00:00:00Z",
            "effective_before": "2026-09-30T23:59:59Z",
        },
    )
    assert [item["id"] for item in september["items"]] == [str(legacy)]

    february = await _list_operations(
        client,
        seed["root_token"],
        params={
            "effective_after": "2026-02-01T00:00:00Z",
            "effective_before": "2026-02-28T23:59:59Z",
        },
    )
    assert [item["id"] for item in february["items"]] == [str(backdated)]


@pytest.mark.asyncio
async def test_created_at_period_filter_remains_available(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The created_at filter capability is not removed: all September-ingested
    operations (including the backdated one) are returned by it."""
    seed = await _seed_fixture(session_factory)

    a = await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 9, 17, 9, 0, tzinfo=UTC),
        effective_at=datetime(2026, 2, 15, 9, 0, tzinfo=UTC),
    )
    b = await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 9, 10, 9, 0, tzinfo=UTC),
        effective_at=datetime(2026, 9, 12, 9, 0, tzinfo=UTC),
    )

    response = await _list_operations(
        client,
        seed["root_token"],
        params={
            "created_after": "2026-09-01T00:00:00Z",
            "created_before": "2026-09-30T23:59:59Z",
        },
    )
    assert {item["id"] for item in response["items"]} == {str(a), str(b)}
    assert response["total_count"] == 2

    outside = await _list_operations(
        client,
        seed["root_token"],
        params={
            "created_after": "2026-10-01T00:00:00Z",
            "created_before": "2026-10-31T23:59:59Z",
        },
    )
    assert outside["items"] == []
