"""Regression tests for issue #24: targeted balances + canonical line identity.

Covers the contracts added on dev for:
- GET /balances?item_ids= targeted filter (B5.1 balances);
- create/update batch canonicalization + duplicate guard (B5.1 create/update);
- >100 line resolve chunking (B4);
- submit-time canonical collision after post-save merge (B5.1 submit);
- reject-all / no partial persistence.

Run: python -m pytest tests/test_operation_issue24.py
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.balance import Balance
from app.models.category import Category
from app.models.inventory_subject import InventorySubject
from app.models.item import Item
from app.models.operation import Operation
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


async def _seed_catalog(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    items: int = 1,
    balance_qty: str | None = "1000.000",
) -> dict:
    """Seed a site, root user, unit, category and `items` active catalog items.

    Each item gets an InventorySubject and (optionally) a Balance on the site.
    Returns site_id, root_token, category_id, unit_id and a list of item dicts.
    """
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"SITE-{suffix}", name=f"Site {suffix}", is_active=True)
        session.add(site)
        await session.flush()

        root = User(
            username=f"root-{suffix}",
            email=f"root-{suffix}@example.com",
            full_name="Root Test",
            is_active=True,
            is_root=True,
            role="root",
            default_site_id=site.id,
        )
        session.add(root)
        await session.flush()

        unit = Unit(code=f"PC-{suffix}", name=f"Piece {suffix}", symbol="pcs", is_active=True)
        category = Category(
            code=f"CAT-{suffix}", name=f"Category {suffix}",
            normalized_name=f"category {suffix}", is_active=True,
        )
        session.add_all([unit, category])
        await session.flush()

        seed_items: list[dict] = []
        for idx in range(items):
            item = Item(
                sku=f"SKU-{suffix}-{idx}",
                name=f"Item {suffix} {idx}",
                normalized_name=f"item {suffix} {idx}",
                category_id=category.id,
                unit_id=unit.id,
                is_active=True,
            )
            session.add(item)
            await session.flush()
            subject = InventorySubject(subject_type="catalog_item", item_id=item.id)
            session.add(subject)
            await session.flush()
            if balance_qty is not None:
                session.add(Balance(
                    site_id=site.id,
                    inventory_subject_id=subject.id,
                    item_id=item.id,
                    qty=Decimal(balance_qty),
                ))
            seed_items.append({"item_id": item.id, "subject_id": subject.id})

        await session.commit()
        return {
            "site_id": site.id,
            "root_token": str(root.user_token),
            "category_id": category.id,
            "unit_id": unit.id,
            "items": seed_items,
        }


def _line(item_id: int, qty: str | int, line_number: int) -> dict:
    return {"line_number": line_number, "item_id": item_id, "qty": qty}


async def _create(client: AsyncClient, token: str, site_id: int, lines: list[dict], op_type: str = "EXPENSE"):
    return await client.post(
        "/api/v1/operations",
        json={"operation_type": op_type, "site_id": site_id, "lines": lines},
        headers={"X-User-Token": token},
    )


# ─── B5.1 Balances: targeted item_ids ──────────────────────────────────────

@pytest.mark.asyncio
async def test_targeted_balances_returns_target_outside_page1(client, session_factory):
    """>100 warehouse rows: a requested id past the default page 1 must be returned."""
    seed = await _seed_catalog(session_factory, items=120)
    target = seed["items"][-1]  # highest id, sorts last under updated_at desc tie
    resp = await client.get(
        f"/api/v1/balances?site_id={seed['site_id']}&item_ids={target['item_id']}",
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["item_id"] == target["item_id"]
    # total_count must reflect the targeted set, not the warehouse-wide list
    assert data["total_count"] == 1


@pytest.mark.asyncio
async def test_targeted_balances_missing_target_returns_empty(client, session_factory):
    seed = await _seed_catalog(session_factory, items=2)
    resp = await client.get(
        f"/api/v1/balances?site_id={seed['site_id']}&item_ids=999999999",
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["items"] == []
    assert data["total_count"] == 0


@pytest.mark.asyncio
async def test_targeted_balances_explicit_zero_row_present(client, session_factory):
    seed = await _seed_catalog(session_factory, items=1, balance_qty="0.000")
    item = seed["items"][0]
    resp = await client.get(
        f"/api/v1/balances?site_id={seed['site_id']}&item_ids={item['item_id']}",
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["items"]) == 1
    assert Decimal(data["items"][0]["qty"]) == Decimal("0")


@pytest.mark.asyncio
async def test_targeted_balances_over_200_rejected(client, session_factory):
    seed = await _seed_catalog(session_factory, items=1)
    ids = ",".join(str(i) for i in range(1, 202))
    resp = await client.get(
        f"/api/v1/balances?site_id={seed['site_id']}&item_ids={ids}",
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_targeted_balances_incompatible_search_rejected(client, session_factory):
    seed = await _seed_catalog(session_factory, items=1)
    resp = await client.get(
        f"/api/v1/balances?site_id={seed['site_id']}&item_ids=1&search=foo",
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_targeted_balances_incompatible_only_positive_rejected(client, session_factory):
    seed = await _seed_catalog(session_factory, items=1)
    resp = await client.get(
        f"/api/v1/balances?site_id={seed['site_id']}&item_ids=1&only_positive=true",
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_targeted_balances_incompatible_category_rejected(client, session_factory):
    seed = await _seed_catalog(session_factory, items=1)
    resp = await client.get(
        f"/api/v1/balances?site_id={seed['site_id']}&item_ids=1&category_id={seed['category_id']}",
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_targeted_balances_legacy_singular_item_id(client, session_factory):
    seed = await _seed_catalog(session_factory, items=1)
    item = seed["items"][0]
    resp = await client.get(
        f"/api/v1/balances?site_id={seed['site_id']}&item_id={item['item_id']}",
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["item_id"] == item["item_id"]


@pytest.mark.asyncio
async def test_targeted_balances_no_pagination_truncation(client, session_factory):
    """150 distinct requested IDs must all be returned, no page truncation."""
    seed = await _seed_catalog(session_factory, items=150)
    ids = [i["item_id"] for i in seed["items"]]
    resp = await client.get(
        f"/api/v1/balances?site_id={seed['site_id']}&item_ids={','.join(map(str, ids))}",
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    returned_ids = {i["item_id"] for i in data["items"]}
    assert returned_ids == set(ids)
    assert data["total_count"] == 150


# ─── B5.1 Create/update: canonicalization + duplicate guard ────────────────

@pytest.mark.asyncio
async def test_create_active_item_ok(client, session_factory):
    seed = await _seed_catalog(session_factory, items=1)
    item = seed["items"][0]
    resp = await _create(client, seed["root_token"], seed["site_id"], [_line(item["item_id"], 1, 1)])
    assert resp.status_code == 200, resp.text
    assert resp.json()["lines"][0]["item_id"] == item["item_id"]


@pytest.mark.asyncio
async def test_create_merged_auto_canonicalizes(client, session_factory):
    seed = await _seed_catalog(session_factory, items=2)
    canonical = seed["items"][0]
    merged = seed["items"][1]
    async with session_factory() as session:
        target = await session.get(Item, merged["item_id"])
        target.merged_into_id = canonical["item_id"]
        target.merged_at = datetime.now(UTC)
        target.is_active = False
        await session.commit()

    resp = await _create(client, seed["root_token"], seed["site_id"], [_line(merged["item_id"], 1, 1)])
    assert resp.status_code == 200, resp.text
    assert resp.json()["lines"][0]["item_id"] == canonical["item_id"]


@pytest.mark.asyncio
async def test_create_missing_item_rejected(client, session_factory):
    seed = await _seed_catalog(session_factory, items=1)
    resp = await _create(client, seed["root_token"], seed["site_id"], [_line(999999999, 1, 1)])
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["code"] == "operation_lines_invalid"
    assert body["lines"][0]["reason"] == "item_not_found"
    assert body["lines"][0]["line_number"] == 1


@pytest.mark.asyncio
async def test_create_deleted_item_rejected(client, session_factory):
    seed = await _seed_catalog(session_factory, items=1)
    item = seed["items"][0]
    async with session_factory() as session:
        target = await session.get(Item, item["item_id"])
        target.deleted_at = datetime.now(UTC)
        await session.commit()

    resp = await _create(client, seed["root_token"], seed["site_id"], [_line(item["item_id"], 1, 1)])
    assert resp.status_code == 409, resp.text
    assert resp.json()["lines"][0]["reason"] == "deleted"


@pytest.mark.asyncio
async def test_create_inactive_item_rejected(client, session_factory):
    seed = await _seed_catalog(session_factory, items=1)
    item = seed["items"][0]
    async with session_factory() as session:
        target = await session.get(Item, item["item_id"])
        target.is_active = False
        await session.commit()

    resp = await _create(client, seed["root_token"], seed["site_id"], [_line(item["item_id"], 1, 1)])
    assert resp.status_code == 409, resp.text
    assert resp.json()["lines"][0]["reason"] == "inactive"


@pytest.mark.asyncio
async def test_create_direct_duplicate_rejected(client, session_factory):
    seed = await _seed_catalog(session_factory, items=1)
    item = seed["items"][0]
    resp = await _create(
        client, seed["root_token"], seed["site_id"],
        [_line(item["item_id"], 1, 1), _line(item["item_id"], 2, 2)],
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["code"] == "operation_lines_invalid"
    dup = [e for e in body["lines"] if e["reason"] == "duplicate_item"]
    assert len(dup) == 1
    assert dup[0]["line_number"] == 2
    assert dup[0]["first_line_number"] == 1


@pytest.mark.asyncio
async def test_create_two_ids_same_canonical_rejected(client, session_factory):
    """Two distinct requested IDs resolving to one canonical → duplicate_item."""
    seed = await _seed_catalog(session_factory, items=3)
    canonical = seed["items"][0]
    merged_b = seed["items"][1]
    merged_c = seed["items"][2]
    async with session_factory() as session:
        for mid in (merged_b["item_id"], merged_c["item_id"]):
            target = await session.get(Item, mid)
            target.merged_into_id = canonical["item_id"]
            target.merged_at = datetime.now(UTC)
            target.is_active = False
        await session.commit()

    resp = await _create(
        client, seed["root_token"], seed["site_id"],
        [_line(merged_b["item_id"], 1, 1), _line(merged_c["item_id"], 1, 2)],
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    dup = [e for e in body["lines"] if e["reason"] == "duplicate_item"]
    assert len(dup) == 1
    assert dup[0]["line_number"] == 2
    assert dup[0]["first_line_number"] == 1


@pytest.mark.asyncio
async def test_create_reject_all_no_partial_persist(client, session_factory):
    """One invalid line rejects the whole operation; nothing is persisted."""
    seed = await _seed_catalog(session_factory, items=1)
    item = seed["items"][0]
    resp = await _create(
        client, seed["root_token"], seed["site_id"],
        [_line(item["item_id"], 1, 1), _line(999999999, 2, 2)],
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    reasons = {e["reason"] for e in body["lines"]}
    assert "item_not_found" in reasons

    async with session_factory() as session:
        count = (await session.execute(select(Operation))).scalars().all()
        assert len(count) == 0, "reject-all must not persist a partial operation"


@pytest.mark.asyncio
async def test_create_over_100_items_chunking(client, session_factory):
    """B4: >100 distinct valid items must not raise a 500."""
    seed = await _seed_catalog(session_factory, items=150)
    lines = [_line(i["item_id"], 1, ln) for ln, i in enumerate(seed["items"], start=1)]
    resp = await _create(client, seed["root_token"], seed["site_id"], lines)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["lines"]) == 150


@pytest.mark.asyncio
async def test_update_over_100_items_chunking(client, session_factory):
    """B4: update with >100 distinct valid items must not raise a 500."""
    seed = await _seed_catalog(session_factory, items=150)
    created = await _create(
        client, seed["root_token"], seed["site_id"],
        [_line(i["item_id"], 1, ln) for ln, i in enumerate(seed["items"], start=1)],
    )
    assert created.status_code == 200, created.text
    op_id = created.json()["id"]

    # Rebuild all 150 lines with new quantities, shuffled order.
    lines = [_line(i["item_id"], 2, ln) for ln, i in enumerate(seed["items"], start=1)]
    resp = await client.patch(
        f"/api/v1/operations/{op_id}",
        json={"lines": lines},
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["lines"]) == 150


@pytest.mark.asyncio
async def test_update_gt100_invalid_item_in_chunk_rejects_all(client, session_factory):
    """An invalid item inside a >100 chunk still yields structured line error (reject-all)."""
    seed = await _seed_catalog(session_factory, items=120)
    created = await _create(
        client, seed["root_token"], seed["site_id"],
        [_line(i["item_id"], 1, ln) for ln, i in enumerate(seed["items"], start=1)],
    )
    assert created.status_code == 200, created.text
    op_id = created.json()["id"]

    lines = [_line(i["item_id"], 2, ln) for ln, i in enumerate(seed["items"], start=1)]
    lines.append(_line(999999999, 1, 121))
    resp = await client.patch(
        f"/api/v1/operations/{op_id}",
        json={"lines": lines},
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["code"] == "operation_lines_invalid"
    assert any(e["reason"] == "item_not_found" and e["line_number"] == 121 for e in body["lines"])


# ─── B5.1 Submit: canonical collision after post-save merge ────────────────

@pytest.mark.asyncio
async def test_submit_merge_after_save_collision_no_effects(client, session_factory):
    """Two distinct items saved, then merged → submit rejects with duplicate_item.

    No balance effects may be applied (reject before side effects).
    """
    seed = await _seed_catalog(session_factory, items=2, balance_qty="1000.000")
    item_a = seed["items"][0]
    item_b = seed["items"][1]
    created = await _create(
        client, seed["root_token"], seed["site_id"],
        [_line(item_a["item_id"], 1, 1), _line(item_b["item_id"], 1, 2)],
    )
    assert created.status_code == 200, created.text
    op_id = created.json()["id"]

    # Post-save: merge item B into item A (as catalog admin would).
    async with session_factory() as session:
        target = await session.get(Item, item_b["item_id"])
        target.merged_into_id = item_a["item_id"]
        target.merged_at = datetime.now(UTC)
        target.is_active = False
        await session.commit()

    resp = await client.post(
        f"/api/v1/operations/{op_id}/submit",
        json={"submit": True},
        headers={"X-User-Token": seed["root_token"]},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["code"] == "operation_lines_invalid"
    dup = [e for e in body["lines"] if e["reason"] == "duplicate_item"]
    assert len(dup) == 1

    # No balance effects applied.
    async with session_factory() as session:
        op = (await session.execute(select(Operation).where(Operation.id == op_id))).scalar_one()
        assert op.status == "draft"
        for item in seed["items"]:
            balance = (await session.execute(
                select(Balance).where(Balance.inventory_subject_id == item["subject_id"])
            )).scalar_one()
            assert balance.qty == Decimal("1000.000"), "submit rejection must not mutate balance"

