from datetime import UTC, datetime, timezone
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


async def _seed_fixture(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"OPS-{suffix}", name=f"Operations Site {suffix}")
        session.add(site)
        await session.flush()

        root_user = User(
            username=f"root-{suffix}",
            email=f"root-{suffix}@example.com",
            full_name="Root User",
            is_active=True,
            is_root=True,
            role="root",
            default_site_id=site.id,
        )
        chief_user = User(
            username=f"chief-{suffix}",
            email=f"chief-{suffix}@example.com",
            full_name="Chief Storekeeper",
            is_active=True,
            is_root=False,
            role="chief_storekeeper",
            default_site_id=site.id,
        )
        storekeeper_user = User(
            username=f"storekeeper-{suffix}",
            email=f"storekeeper-{suffix}@example.com",
            full_name="Storekeeper",
            is_active=True,
            is_root=False,
            role="storekeeper",
            default_site_id=site.id,
        )
        session.add_all([root_user, chief_user, storekeeper_user])
        await session.flush()

        session.add(
            UserAccessScope(
                user_id=storekeeper_user.id,
                site_id=site.id,
                can_view=True,
                can_operate=True,
                can_manage_catalog=False,
                is_active=True,
            )
        )

        unit = Unit(code=f"PCS{suffix}", name=f"Piece {suffix}", symbol=f"P{suffix}", is_active=True)
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
            is_active=True,
        )
        session.add(item)
        await session.commit()

        return {
            "site_id": site.id,
            "item_id": item.id,
            "root_token": str(root_user.user_token),
            "chief_token": str(chief_user.user_token),
            "storekeeper_token": str(storekeeper_user.user_token),
        }


async def _create_operation(client: AsyncClient, *, token: str, site_id: int, item_id: int) -> dict:
    response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": token},
        json={
            "operation_type": "RECEIVE",
            "site_id": site_id,
            "lines": [{"line_number": 1, "item_id": item_id, "qty": 5}],
            "notes": "incoming",
        },
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_create_operation_sets_default_effective_at(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)

    operation = await _create_operation(
        client,
        token=seed["storekeeper_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    assert operation["effective_at"] is not None


@pytest.mark.asyncio
async def test_create_operation_accepts_explicit_effective_at(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)
    effective_at = datetime(2026, 1, 19, 8, 15, tzinfo=timezone.utc)

    response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "effective_at": effective_at.isoformat(),
            "lines": [{"line_number": 1, "item_id": seed["item_id"], "qty": 5}],
        },
    )

    assert response.status_code == 200
    assert datetime.fromisoformat(response.json()["effective_at"]) == effective_at


@pytest.mark.asyncio
async def test_general_patch_accepts_effective_at_atomically(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """TZ-V3.2 B3: PATCH now accepts effective_at atomically with other fields.

    The dedicated /effective-at endpoint remains for legacy compatibility.
    """
    seed = await _seed_fixture(session_factory)
    operation = await _create_operation(
        client,
        token=seed["storekeeper_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    new_effective_at = datetime(2026, 1, 20, 10, 30, tzinfo=UTC)
    response = await client.patch(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"effective_at": new_effective_at.isoformat()},
    )

    assert response.status_code == 200
    assert datetime.fromisoformat(response.json()["effective_at"]) == new_effective_at
    # version is incremented atomically with effective_at update
    assert response.json()["version"] >= 2


@pytest.mark.asyncio
async def test_storekeeper_can_change_effective_at_for_own_draft(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)
    operation = await _create_operation(
        client,
        token=seed["storekeeper_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    new_effective_at = datetime(2026, 1, 21, 10, 30, tzinfo=timezone.utc)
    response = await client.patch(
        f"/api/v1/operations/{operation['id']}/effective-at",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"effective_at": new_effective_at.isoformat()},
    )

    assert response.status_code == 200
    assert datetime.fromisoformat(response.json()["effective_at"]) == new_effective_at


@pytest.mark.asyncio
async def test_storekeeper_cannot_change_effective_at_after_submit(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seed = await _seed_fixture(session_factory)
    operation = await _create_operation(
        client,
        token=seed["storekeeper_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    submit_response = await client.post(
        f"/api/v1/operations/{operation['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_response.status_code == 200

    response = await client.patch(
        f"/api/v1/operations/{operation['id']}/effective-at",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"effective_at": datetime(2026, 1, 21, 10, 30, tzinfo=timezone.utc).isoformat()},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "only chief_storekeeper, root, or draft creator may change operation effective_at"


@pytest.mark.asyncio
async def test_chief_storekeeper_cannot_change_effective_at_for_submitted_operation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """ADR-0028 §2: effective_at is draft-only mutable. Chief on a submitted
    operation must receive 409 from the workflow guard, even when permission
    is granted (chief has global access; permission guard passes, workflow
    guard fails).
    """
    seed = await _seed_fixture(session_factory)
    operation = await _create_operation(
        client,
        token=seed["storekeeper_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    submit_response = await client.post(
        f"/api/v1/operations/{operation['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_response.status_code == 200

    new_effective_at = datetime(2026, 1, 22, 9, 45, tzinfo=timezone.utc)
    update_response = await client.patch(
        f"/api/v1/operations/{operation['id']}/effective-at",
        headers={"X-User-Token": seed["chief_token"]},
        json={"effective_at": new_effective_at.isoformat()},
    )

    assert update_response.status_code == 409
    assert "effective_at" in update_response.json()["detail"]
    # operation was NOT mutated
    refresh = await client.get(
        f"/api/v1/operations/{operation['id']}",
        headers={"X-User-Token": seed["chief_token"]},
    )
    assert refresh.status_code == 200
    assert refresh.json()["status"] == "submitted"
    assert refresh.json()["effective_at"] != new_effective_at.isoformat()


@pytest.mark.asyncio
async def test_root_cannot_change_effective_at_for_cancelled_operation(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """ADR-0028 §2: cancelled operations are fail-closed for effective_at."""
    seed = await _seed_fixture(session_factory)
    operation = await _create_operation(
        client,
        token=seed["root_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    submit_response = await client.post(
        f"/api/v1/operations/{operation['id']}/submit",
        headers={"X-User-Token": seed["root_token"]},
        json={"submit": True},
    )
    assert submit_response.status_code == 200

    cancel_response = await client.post(
        f"/api/v1/operations/{operation['id']}/cancel",
        headers={"X-User-Token": seed["root_token"]},
        json={"cancel": True, "reason": "test"},
    )
    assert cancel_response.status_code == 200

    update_response = await client.patch(
        f"/api/v1/operations/{operation['id']}/effective-at",
        headers={"X-User-Token": seed["root_token"]},
        json={"effective_at": datetime(2026, 1, 23, 12, 0, tzinfo=timezone.utc).isoformat()},
    )

    assert update_response.status_code == 409
    assert "effective_at" in update_response.json()["detail"]


@pytest.mark.asyncio
async def test_root_can_change_effective_at_for_restored_draft(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """ADR-0028 §2: restored operations are draft again and accept effective_at."""
    seed = await _seed_fixture(session_factory)
    operation = await _create_operation(
        client,
        token=seed["root_token"],
        site_id=seed["site_id"],
        item_id=seed["item_id"],
    )

    submit_response = await client.post(
        f"/api/v1/operations/{operation['id']}/submit",
        headers={"X-User-Token": seed["root_token"]},
        json={"submit": True},
    )
    assert submit_response.status_code == 200

    cancel_response = await client.post(
        f"/api/v1/operations/{operation['id']}/cancel",
        headers={"X-User-Token": seed["root_token"]},
        json={"cancel": True, "reason": "test"},
    )
    assert cancel_response.status_code == 200

    restore_response = await client.post(
        f"/api/v1/operations/{operation['id']}/restore",
        headers={"X-User-Token": seed["root_token"]},
        json={"restore": True},
    )
    assert restore_response.status_code == 200
    assert restore_response.json()["status"] == "draft"

    new_effective_at = datetime(2026, 1, 24, 9, 0, tzinfo=timezone.utc)
    update_response = await client.patch(
        f"/api/v1/operations/{operation['id']}/effective-at",
        headers={"X-User-Token": seed["root_token"]},
        json={"effective_at": new_effective_at.isoformat()},
    )

    assert update_response.status_code == 200
    assert datetime.fromisoformat(update_response.json()["effective_at"]) == new_effective_at
