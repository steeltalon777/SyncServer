"""Release-blocker regression: default /operations list must use business
chronology (``effective_at DESC``), not ingestion chronology (``created_at``).

Scenario that motivated the fix: historical operations imported today
(created_at = today, effective_at = January) must appear among January
operations, not at the top of the list.

Covered here:
- primary key: COALESCE(effective_at, created_at) DESC;
- NULL effective_at fallback to created_at (legacy rows);
- deterministic tie-breakers: created_at DESC, then id DESC;
- pagination boundaries use the same canonical order and a newly inserted
  backdated operation does not jump onto page 1.
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
        site = Site(code=f"EFF-ORDER-{suffix}", name=f"Effective Order Site {suffix}")
        session.add(site)
        await session.flush()

        root_user = User(
            username=f"root-eff-order-{suffix}",
            email=f"root-eff-order-{suffix}@example.com",
            full_name="Root Effective Order",
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
    page: int = 1,
    page_size: int = 50,
) -> dict:
    response = await client.get(
        "/api/v1/operations",
        headers={"X-User-Token": token},
        params={"page": page, "page_size": page_size},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_default_list_order_follows_effective_at_not_created_at(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A/B/C/D scenario: created_at order != effective_at order.

    Ingestion (created_at): D(Mar, NULL eff) < C(Jun) < A(Sep) < ... and
    B ingested first in January but backdated business date September.
    Business chronology (effective_at, NULL -> created_at):
    B(Sep) > C(Jun) > D(Mar fallback) > A(Jan).
    A created_at-ordered list would yield A, C, D, B and fail this test.
    """
    seed = await _seed_fixture(session_factory)

    b = await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 1, 10, 9, 0, tzinfo=UTC),
        effective_at=datetime(2026, 9, 10, 9, 0, tzinfo=UTC),
    )
    c = await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
        effective_at=datetime(2026, 6, 20, 9, 0, tzinfo=UTC),
    )
    a = await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 9, 16, 9, 0, tzinfo=UTC),
        effective_at=datetime(2026, 1, 15, 9, 0, tzinfo=UTC),
    )
    d = await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
        effective_at=None,
    )

    body = await _list_operations(client, seed["root_token"])
    ids = [item["id"] for item in body["items"]]

    assert ids == [str(b), str(c), str(d), str(a)]
    assert body["total_count"] == 4


@pytest.mark.asyncio
async def test_pagination_keeps_effective_chronology_and_backdated_op_stays_off_page_one(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Page boundaries must use the canonical order before offset/limit.

    A backdated operation inserted later (created_at = latest) must appear on
    the last page, never on page 1. Walking all pages must not duplicate or
    skip rows.
    """
    seed = await _seed_fixture(session_factory)

    e1 = await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
        effective_at=datetime(2026, 9, 10, 9, 0, tzinfo=UTC),
    )
    e2 = await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 1, 6, 9, 0, tzinfo=UTC),
        effective_at=datetime(2026, 6, 20, 9, 0, tzinfo=UTC),
    )
    e3 = await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
        effective_at=None,
    )
    e4 = await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 8, 1, 9, 0, tzinfo=UTC),
        effective_at=datetime(2026, 1, 15, 9, 0, tzinfo=UTC),
    )
    e5 = await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 8, 2, 9, 0, tzinfo=UTC),
        effective_at=datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
    )

    page1 = await _list_operations(client, seed["root_token"], page=1, page_size=2)
    page2 = await _list_operations(client, seed["root_token"], page=2, page_size=2)
    page3 = await _list_operations(client, seed["root_token"], page=3, page_size=2)

    assert [item["id"] for item in page1["items"]] == [str(e1), str(e2)]
    assert [item["id"] for item in page2["items"]] == [str(e3), str(e4)]
    assert [item["id"] for item in page3["items"]] == [str(e5)]

    # Historical import entered today with a January business date.
    backdated = await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 9, 16, 9, 0, tzinfo=UTC),
        effective_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
    )

    page1_after = await _list_operations(client, seed["root_token"], page=1, page_size=2)
    page2_after = await _list_operations(client, seed["root_token"], page=2, page_size=2)
    page3_after = await _list_operations(client, seed["root_token"], page=3, page_size=2)

    assert [item["id"] for item in page1_after["items"]] == [str(e1), str(e2)]
    assert str(backdated) not in [item["id"] for item in page1_after["items"]]
    assert [item["id"] for item in page2_after["items"]] == [str(e3), str(e4)]
    assert [item["id"] for item in page3_after["items"]] == [str(e5), str(backdated)]
    assert page1_after["total_count"] == 6

    walked_ids = [
        item["id"]
        for page in (page1_after, page2_after, page3_after)
        for item in page["items"]
    ]
    assert walked_ids == [str(e1), str(e2), str(e3), str(e4), str(e5), str(backdated)]
    assert len(walked_ids) == len(set(walked_ids)) == 6


@pytest.mark.asyncio
async def test_default_list_has_deterministic_tie_breakers(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Equal effective_at must not reorder arbitrarily.

    Tie-break chain: effective_at DESC, created_at DESC, id DESC.
    - t1/t2 share effective_at; t1 was created later -> t1 first, even though
      its id is lexicographically smaller.
    - u1/u2 share effective_at AND created_at -> id DESC decides.
    """
    seed = await _seed_fixture(session_factory)

    shared_effective = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)

    t1 = UUID("00000000-0000-4000-8000-000000000001")
    t2 = UUID("00000000-0000-4000-8000-000000000002")
    u1 = UUID("00000000-0000-4000-8000-000000000003")
    u2 = UUID("00000000-0000-4000-8000-000000000004")

    await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 5, 2, 9, 0, tzinfo=UTC),
        effective_at=shared_effective,
        operation_id=t1,
    )
    await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 5, 1, 9, 0, tzinfo=UTC),
        effective_at=shared_effective,
        operation_id=t2,
    )
    await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
        effective_at=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
        operation_id=u1,
    )
    await _add_operation(
        session_factory,
        site_id=seed["site_id"],
        user_id=seed["root_user_id"],
        created_at=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
        effective_at=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
        operation_id=u2,
    )

    body = await _list_operations(client, seed["root_token"])
    ids = [item["id"] for item in body["items"]]

    assert ids == [str(t1), str(t2), str(u2), str(u1)]
