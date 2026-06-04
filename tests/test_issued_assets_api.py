from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.asset_register import IssuedAssetBalance
from app.models.category import Category
from app.models.inventory_subject import InventorySubject
from app.models.issue_object import IssueObject
from app.models.issue_object_category import IssueObjectCategory
from app.models.item import Item
from app.models.site import Site
from app.models.unit import Unit
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


async def _seed_fixture(session_factory: async_sessionmaker[AsyncSession]) -> dict:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"SITE-{suffix}", name=f"Site {suffix}")
        session.add(site)
        await session.flush()

        storekeeper = User(
            username=f"sk-{suffix}",
            email=f"sk-{suffix}@example.com",
            full_name="Storekeeper",
            is_active=True,
            is_root=False,
            role="storekeeper",
            default_site_id=site.id,
        )
        session.add(storekeeper)
        await session.flush()

        cat_a = IssueObjectCategory(
            name=f"Category A {suffix}",
            normalized_key=f"category_a_{suffix}",
            sort_order=0, is_active=True,
        )
        cat_b = IssueObjectCategory(
            name=f"Category B {suffix}",
            normalized_key=f"category_b_{suffix}",
            sort_order=1, is_active=True,
        )
        session.add_all([cat_a, cat_b])
        await session.flush()

        import re
        _non_word_re = re.compile(r"[^\w\s]+", flags=re.UNICODE)
        _spaces_re = re.compile(r"\s+", flags=re.UNICODE)
        def _norm(v): return _spaces_re.sub(" ", _non_word_re.sub(" ", (v or "").strip().lower().replace("ё", "е"))).strip()

        obj_a = IssueObject(
            display_name=f"Object A {suffix}",
            normalized_key=_norm(f"Object A {suffix}"),
            object_type="person", is_active=True,
            category_id=cat_a.id,
        )
        obj_b = IssueObject(
            display_name=f"Object B {suffix}",
            normalized_key=_norm(f"Object B {suffix}"),
            object_type="person", is_active=True,
            category_id=cat_b.id,
        )
        session.add_all([obj_a, obj_b])
        await session.flush()

        catalog_cat = Category(
            name=f"Catalog Cat {suffix}",
            normalized_name=f"catalog_cat_{suffix}",
            is_active=True,
        )
        session.add(catalog_cat)
        await session.flush()

        unit = Unit(
            code=f"PC-{suffix}", name=f"Piece {suffix}",
            symbol=f"pc{suffix[:3]}", is_active=True,
        )
        session.add(unit)
        await session.flush()

        item_a = Item(
            sku=f"SKU-A-{suffix}", name=f"Item A {suffix}",
            normalized_name=f"item_a_{suffix}",
            category_id=catalog_cat.id,
            unit_id=unit.id,
            is_active=True,
        )
        item_b = Item(
            sku=f"SKU-B-{suffix}", name=f"Item B {suffix}",
            normalized_name=f"item_b_{suffix}",
            category_id=catalog_cat.id,
            unit_id=unit.id,
            is_active=True,
        )
        session.add_all([item_a, item_b])
        await session.flush()

        inv_a = InventorySubject(subject_type="catalog_item", item_id=item_a.id)
        inv_b = InventorySubject(subject_type="catalog_item", item_id=item_b.id)
        session.add_all([inv_a, inv_b])
        await session.flush()

        bal_a = IssuedAssetBalance(
            issue_object_id=obj_a.id,
            inventory_subject_id=inv_a.id,
            qty=Decimal("5.000"),
        )
        bal_b = IssuedAssetBalance(
            issue_object_id=obj_b.id,
            inventory_subject_id=inv_b.id,
            qty=Decimal("3.000"),
        )
        session.add_all([bal_a, bal_b])
        await session.commit()

        return {
            "token": str(storekeeper.user_token),
            "cat_a_id": cat_a.id,
            "cat_b_id": cat_b.id,
            "obj_a_id": obj_a.id,
            "obj_b_id": obj_b.id,
        }


@pytest.mark.asyncio
async def test_issued_assets_filter_by_category_id(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    seed = await _seed_fixture(session_factory)

    response = await client.get(
        "/api/v1/issued-assets",
        headers={"X-User-Token": seed["token"]},
        params={"category_id": seed["cat_a_id"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] >= 1
    assert all(row["issue_object_id"] == seed["obj_a_id"] for row in data["items"])

    response = await client.get(
        "/api/v1/issued-assets",
        headers={"X-User-Token": seed["token"]},
        params={"category_id": seed["cat_b_id"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] >= 1
    assert all(row["issue_object_id"] == seed["obj_b_id"] for row in data["items"])

    response = await client.get(
        "/api/v1/issued-assets",
        headers={"X-User-Token": seed["token"]},
        params={"category_id": 99999},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 0
