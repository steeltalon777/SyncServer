"""D2 list action-state contract tests.

``GET /api/v1/review-items`` must return server-computed per-item action state
inside the list DTO:

* ``total_balance`` — authoritative sum over inventory subject balance rows;
* ``has_pending_acceptance`` — pending acceptance only (qty > 0);
* ``has_active_registers`` — backend enforcement predicate pending|lost|issued.

All three are aggregated for the whole page with a constant number of SQL
queries (no N+1). See
``docs/reviews/architecture-review-review-item-backend-hardening.md`` (D2).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models.asset_register import (
    IssuedAssetBalance,
    LostAssetBalance,
    PendingAcceptanceBalance,
)
from app.models.balance import Balance
from app.models.category import Category
from app.models.inventory_subject import InventorySubject
from app.models.issue_object import IssueObject
from app.models.issue_object_category import IssueObjectCategory
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


def _norm(value: str) -> str:
    import re

    non_word = re.compile(r"[^\w\s]+", flags=re.UNICODE)
    spaces = re.compile(r"\s+", flags=re.UNICODE)
    return spaces.sub(" ", non_word.sub(" ", (value or "").strip().lower().replace("ё", "е"))).strip()


async def _seed(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"D2-{suffix}", name=f"D2 Site {suffix}", is_active=True)
        session.add(site)
        await session.flush()

        chief = User(
            username=f"d2-chief-{suffix}",
            email=f"d2-chief-{suffix}@example.com",
            full_name="D2 Chief",
            is_active=True,
            is_root=False,
            role="chief_storekeeper",
            default_site_id=site.id,
        )
        storekeeper = User(
            username=f"d2-sk-{suffix}",
            email=f"d2-sk-{suffix}@example.com",
            full_name="D2 Storekeeper",
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

        unit = Unit(code=f"D2U-{suffix}", name=f"D2 Unit {suffix}", symbol=f"d{suffix[:2]}", is_active=True)
        category = Category(
            code=f"D2C-{suffix}",
            name=f"D2 Category {suffix}",
            normalized_name=f"d2 category {suffix}",
            is_active=True,
        )
        session.add_all([unit, category])
        await session.flush()

        issue_object_category = IssueObjectCategory(
            name=f"D2 People {suffix}",
            normalized_key=_norm(f"D2 People {suffix}"),
            sort_order=0,
            is_active=True,
        )
        session.add(issue_object_category)
        await session.flush()

        issue_object = IssueObject(
            display_name=f"D2 Employee-{suffix}",
            normalized_key=_norm(f"D2 Employee-{suffix}"),
            object_type="person",
            is_active=True,
            category_id=issue_object_category.id,
        )
        session.add(issue_object)
        await session.commit()

        return {
            "site_id": site.id,
            "chief_token": str(chief.user_token),
            "storekeeper_token": str(storekeeper.user_token),
            "unit_id": unit.id,
            "category_id": category.id,
            "issue_object_id": issue_object.id,
        }


async def _receive(
    client: AsyncClient,
    seed: dict[str, object],
    *,
    qty: int,
    key: str,
) -> tuple[dict, int]:
    """RECEIVE an inline temporary item, submit it, return (operation, review_item_id)."""
    create_resp = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "RECEIVE",
            "site_id": seed["site_id"],
            "client_request_id": key,
            "lines": [
                {
                    "line_number": 1,
                    "qty": qty,
                    "temporary_item": {
                        "client_key": key,
                        "name": f"D2 Temp {key}",
                        "sku": None,
                        "unit_id": seed["unit_id"],
                        "category_id": seed["category_id"],
                    },
                },
            ],
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    op = create_resp.json()

    submit_resp = await client.post(
        f"/api/v1/operations/{op['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_resp.status_code == 200, submit_resp.text
    review_item_id = submit_resp.json()["lines"][0]["item_id"]
    assert review_item_id is not None
    return op, int(review_item_id)


async def _accept(
    client: AsyncClient,
    seed: dict[str, object],
    op: dict,
    *,
    accepted: int,
    lost: int = 0,
) -> None:
    resp = await client.post(
        f"/api/v1/operations/{op['id']}/accept-lines",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "lines": [
                {"line_id": op["lines"][0]["id"], "accepted_qty": accepted, "lost_qty": lost},
            ]
        },
    )
    assert resp.status_code == 200, resp.text


async def _issue(
    client: AsyncClient,
    seed: dict[str, object],
    review_item_id: int,
    *,
    qty: int,
) -> None:
    create_resp = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "ISSUE",
            "site_id": seed["site_id"],
            "issue_object_id": seed["issue_object_id"],
            "lines": [{"line_number": 1, "item_id": review_item_id, "qty": qty}],
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    op = create_resp.json()
    submit_resp = await client.post(
        f"/api/v1/operations/{op['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_resp.status_code == 200, submit_resp.text


async def _write_off(
    client: AsyncClient,
    seed: dict[str, object],
    review_item_id: int,
    *,
    qty: int,
) -> None:
    create_resp = await client.post(
        "/api/v1/operations",
        headers={"X-User-Token": seed["storekeeper_token"]},
        json={
            "operation_type": "WRITE_OFF",
            "site_id": seed["site_id"],
            "lines": [{"line_number": 1, "item_id": review_item_id, "qty": qty}],
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    op = create_resp.json()
    submit_resp = await client.post(
        f"/api/v1/operations/{op['id']}/submit",
        headers={"X-User-Token": seed["chief_token"]},
        json={"submit": True},
    )
    assert submit_resp.status_code == 200, submit_resp.text


async def _list_body(client: AsyncClient, seed: dict[str, object]) -> dict:
    resp = await client.get(
        "/api/v1/review-items",
        headers={"X-User-Token": seed["chief_token"]},
        params={"page": 1, "page_size": 50},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _db_state(
    session_factory: async_sessionmaker[AsyncSession],
    item_id: int,
) -> dict[str, Decimal]:
    async with session_factory() as session:
        subject_id = (
            await session.execute(
                select(InventorySubject.id).where(InventorySubject.item_id == item_id)
            )
        ).scalar_one()

        async def _sum(model) -> Decimal:
            value = (
                await session.execute(
                    select(func.coalesce(func.sum(model.qty), 0)).where(
                        model.inventory_subject_id == subject_id
                    )
                )
            ).scalar_one()
            return Decimal(str(value))

        return {
            "total_balance": await _sum(Balance),
            "pending": await _sum(PendingAcceptanceBalance),
            "lost": await _sum(LostAssetBalance),
            "issued": await _sum(IssuedAssetBalance),
        }


def _attach_query_counter(session_factory: async_sessionmaker[AsyncSession]):
    engine = session_factory.kw["bind"]
    counts = {"n": 0}

    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        counts["n"] += 1

    event.listen(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)
    return counts, lambda: event.remove(
        engine.sync_engine, "before_cursor_execute", _before_cursor_execute
    )


@pytest.mark.asyncio
async def test_list_review_items_action_state_contract(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """List DTO exposes server-computed balance/register state per item."""
    seed = await _seed(session_factory)

    op_zero, zero_id = await _receive(client, seed, qty=4, key="d2-zero")
    await _accept(client, seed, op_zero, accepted=4)
    await _write_off(client, seed, zero_id, qty=4)

    op_pos, pos_id = await _receive(client, seed, qty=5, key="d2-pos")
    await _accept(client, seed, op_pos, accepted=5)

    _, pending_id = await _receive(client, seed, qty=3, key="d2-pending")

    op_lost, lost_id = await _receive(client, seed, qty=5, key="d2-lost")
    await _accept(client, seed, op_lost, accepted=0, lost=5)

    op_issued, issued_id = await _receive(client, seed, qty=5, key="d2-issued")
    await _accept(client, seed, op_issued, accepted=5)
    await _issue(client, seed, issued_id, qty=2)

    op_combo, combo_id = await _receive(client, seed, qty=8, key="d2-combo")
    await _accept(client, seed, op_combo, accepted=3, lost=2)

    body = await _list_body(client, seed)
    assert body["total_count"] == 6
    assert body["page"] == 1
    assert body["page_size"] == 50

    by_id = {item["id"]: item for item in body["items"]}
    assert set(by_id) == {zero_id, pos_id, pending_id, lost_id, issued_id, combo_id}

    expected = {
        zero_id: ("0.000", False, False),
        pos_id: ("5.000", False, False),
        pending_id: ("0.000", True, True),
        lost_id: ("0.000", False, True),
        combo_id: ("3.000", True, True),
    }
    for item_id, (balance, pending, active) in expected.items():
        item = by_id[item_id]
        assert isinstance(item["total_balance"], str)
        assert isinstance(item["has_pending_acceptance"], bool)
        assert isinstance(item["has_active_registers"], bool)
        assert Decimal(item["total_balance"]) == Decimal(balance), item
        assert item["has_pending_acceptance"] is pending, item
        assert item["has_active_registers"] is active, item

    issued = by_id[issued_id]
    assert issued["has_pending_acceptance"] is False
    assert issued["has_active_registers"] is True

    # Every list field must match the authoritative register/balance rows.
    for item_id, item in by_id.items():
        state = await _db_state(session_factory, item_id)
        assert Decimal(item["total_balance"]) == state["total_balance"], item_id
        assert item["has_pending_acceptance"] == (state["pending"] > 0), item_id
        assert item["has_active_registers"] == (
            state["pending"] > 0 or state["lost"] > 0 or state["issued"] > 0
        ), item_id

    # list/detail parity: list total_balance equals the detail balance sum.
    for item_id, expected_total in ((pos_id, Decimal("5.000")), (combo_id, Decimal("3.000"))):
        detail = await client.get(
            f"/api/v1/review-items/{item_id}",
            headers={"X-User-Token": seed["chief_token"]},
        )
        assert detail.status_code == 200, detail.text
        detail_total = sum(
            (Decimal(str(row["qty"])) for row in detail.json()["balances_per_site"]),
            Decimal("0"),
        )
        assert detail_total == expected_total


@pytest.mark.asyncio
async def test_list_review_items_page_query_count_is_constant(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Page aggregation uses a constant number of SQL queries (no N+1)."""
    seed = await _seed(session_factory)

    op_one, _ = await _receive(client, seed, qty=5, key="d2-q1")
    await _accept(client, seed, op_one, accepted=5)

    counts_one, detach_one = _attach_query_counter(session_factory)
    body_one = await _list_body(client, seed)
    detach_one()
    assert body_one["total_count"] == 1

    op_two, two_id = await _receive(client, seed, qty=4, key="d2-q2")
    await _accept(client, seed, op_two, accepted=4)
    await _write_off(client, seed, two_id, qty=4)
    await _receive(client, seed, qty=3, key="d2-q3")
    op_four, _ = await _receive(client, seed, qty=5, key="d2-q4")
    await _accept(client, seed, op_four, accepted=0, lost=5)
    op_five, five_id = await _receive(client, seed, qty=5, key="d2-q5")
    await _accept(client, seed, op_five, accepted=5)
    await _issue(client, seed, five_id, qty=2)
    op_six, _ = await _receive(client, seed, qty=8, key="d2-q6")
    await _accept(client, seed, op_six, accepted=3, lost=2)

    counts_many, detach_many = _attach_query_counter(session_factory)
    body_many = await _list_body(client, seed)
    detach_many()
    assert body_many["total_count"] == 6

    assert counts_many["n"] == counts_one["n"], (
        f"query count grew with page size: {counts_one['n']} -> {counts_many['n']}"
    )
