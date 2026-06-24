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

app = create_app()


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


async def _seed(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"ST-{suffix}", name=f"Site {suffix}")
        session.add(site)
        await session.flush()

        chief = User(
            username=f"chief-{suffix}",
            email=f"chief-{suffix}@example.com",
            full_name="Chief",
            is_active=True,
            is_root=False,
            role="chief_storekeeper",
            default_site_id=site.id,
        )
        storekeeper = User(
            username=f"storekeeper-{suffix}",
            email=f"storekeeper-{suffix}@example.com",
            full_name="Storekeeper",
            is_active=True,
            is_root=False,
            role="storekeeper",
            default_site_id=site.id,
        )
        session.add_all([chief, storekeeper])
        await session.flush()

        session.add_all(
            [
                UserAccessScope(
                    user_id=chief.id,
                    site_id=site.id,
                    can_view=True,
                    can_operate=True,
                    can_manage_catalog=True,
                    is_active=True,
                ),
                UserAccessScope(
                    user_id=storekeeper.id,
                    site_id=site.id,
                    can_view=True,
                    can_operate=True,
                    can_manage_catalog=False,
                    is_active=True,
                ),
            ]
        )

        unit = Unit(code=f"U-{suffix}", name=f"Unit {suffix}", symbol=f"u{suffix[:2]}", is_active=True)
        category = Category(code=f"C-{suffix}", name=f"Category {suffix}", normalized_name=f"category {suffix}", is_active=True)
        session.add_all([unit, category])
        await session.flush()

        existing_sku = f"SKU-{suffix}"
        catalog_item = Item(
            sku=existing_sku,
            name=f"Catalog Item {suffix}",
            normalized_name=f"catalog item {suffix}",
            category_id=category.id,
            unit_id=unit.id,
            is_active=True,
        )
        session.add(catalog_item)
        await session.commit()
        return {
            "site_id": site.id,
            "chief_token": str(chief.user_token),
            "storekeeper_token": str(storekeeper.user_token),
            "category_id": category.id,
            "unit_id": unit.id,
            "catalog_item_id": catalog_item.id,
            "existing_sku": existing_sku,
        }


async def _create_draft_with_inline(
    client: AsyncClient,
    seed: dict[str, object],
    sku: str | None,
    client_request_id: str,
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": client_request_id,
            "lines": [
                {
                    "line_number": 1,
                    "qty": 2,
                    "temporary_item": {
                        "client_key": "inline-1",
                        "name": "Inline review item",
                        "sku": sku,
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                        "description": None,
                        "hashtags": None,
                    },
                },
            ],
        },
    )
    return {"status_code": response.status_code, "body": response.json()}


@pytest.mark.asyncio
async def test_create_draft_with_duplicate_sku_returns_409(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """При создании draft с inline ТМЦ, SKU которого уже занят, возвращается 409."""
    seed = await _seed(session_factory)
    result = await _create_draft_with_inline(
        client, seed, sku=seed["existing_sku"], client_request_id="dup-draft-1"
    )
    assert result["status_code"] == 409
    detail = result["body"]["detail"]
    assert seed["existing_sku"] in detail
    assert "уже занят" in detail


@pytest.mark.asyncio
async def test_update_draft_with_duplicate_sku_returns_409(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """При обновлении draft добавлением inline ТМЦ с занятым SKU возвращается 409."""
    seed = await _seed(session_factory)

    # Создаём draft без SKU
    create_result = await _create_draft_with_inline(
        client, seed, sku=None, client_request_id="update-draft-1"
    )
    assert create_result["status_code"] == 200
    operation_id = create_result["body"]["id"]

    response = await client.patch(
        f"/api/v1/operations/{operation_id}",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "lines": [
                {
                    "line_number": 1,
                    "qty": 2,
                    "temporary_item": {
                        "client_key": "inline-2",
                        "name": "Inline review item with dup sku",
                        "sku": seed["existing_sku"],
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                },
            ],
        },
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert seed["existing_sku"] in detail
    assert "уже занят" in detail


@pytest.mark.asyncio
async def test_submit_with_duplicate_sku_returns_409(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Если SKU inline ТМЦ стал занят между созданием draft и submit, возвращается 409."""
    seed = await _seed(session_factory)

    create_result = await _create_draft_with_inline(
        client, seed, sku="UNIQUE-SKU-12345", client_request_id="submit-dup-1"
    )
    assert create_result["status_code"] == 200
    operation_id = create_result["body"]["id"]

    # Между созданием draft и submit другой процесс занимает этот SKU
    async with session_factory() as session:
        existing = Item(
            sku="UNIQUE-SKU-12345",
            name="Intercepted SKU item",
            normalized_name="intercepted sku item",
            category_id=seed["category_id"],
            unit_id=seed["unit_id"],
            is_active=True,
        )
        session.add(existing)
        await session.commit()

    response = await client.post(
        f"/api/v1/operations/{operation_id}/submit",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"submit": True},
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "UNIQUE-SKU-12345" in detail
    assert "уже занят" in detail


@pytest.mark.asyncio
async def test_submit_with_valid_inline_sku_succeeds(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Submit с уникальным SKU inline ТМЦ успешно завершается."""
    seed = await _seed(session_factory)

    create_result = await _create_draft_with_inline(
        client, seed, sku=f"UNIQUE-{uuid4().hex[:8]}", client_request_id="valid-submit-1"
    )
    assert create_result["status_code"] == 200
    operation_id = create_result["body"]["id"]

    response = await client.post(
        f"/api/v1/operations/{operation_id}/submit",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={"submit": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "submitted"
