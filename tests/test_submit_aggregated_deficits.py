"""DB-backed integration tests for the aggregated submit balance check (TZ §12).

Covers the two-phase aggregation algorithm (ADR-0025 §5, TZ §5):
- one `get_for_update` per unique balance key, in global sorted order;
- all lines of a group reported together even when one line alone is
  sufficient;
- deterministic `errors[]` order by the first line's line_number;
- the authoritative state-before-version guard order (TZ §7.1);
- the ProblemEnvelope response for every submit domain error.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_db
from app.models import IssuedAssetBalance
from app.models.balance import Balance
from app.models.category import Category
from app.models.inventory_subject import InventorySubject
from app.models.issue_object import IssueObject
from app.models.issue_object_category import IssueObjectCategory
from app.models.item import Item
from app.models.site import Site
from app.models.unit import Unit
from app.models.user import User
from app.repos.balances_repo import BalancesRepo
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


async def _seed(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    item_balances: list[tuple[str, str]] | None = None,
    second_site: bool = False,
    include_issue_object: bool = False,
    issued_qty: str = "0.000",
) -> dict:
    """Seed sites, users, units, categories, items, subjects and balances."""
    item_balances = item_balances or [("Item A", "80.000")]
    async with session_factory() as session:
        suffix = uuid4().hex[:6]
        site = Site(code=f"SITE-{suffix}", name=f"Site {suffix}", is_active=True)
        session.add(site)
        await session.flush()

        second_site_obj = None
        if second_site:
            second_site_obj = Site(code=f"DEST-{suffix}", name=f"Dest {suffix}", is_active=True)
            session.add(second_site_obj)
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
        observer = User(
            username=f"obs-{suffix}",
            email=f"obs-{suffix}@example.com",
            full_name="Observer Test",
            is_active=True,
            is_root=False,
            role="observer",
        )
        session.add_all([root, observer])
        await session.flush()

        unit = Unit(
            code=f"PC-{suffix}",
            name=f"Piece {suffix}",
            symbol=f"pc{suffix[:3]}",
            is_active=True,
        )
        category = Category(
            code=f"CAT-{suffix}",
            name=f"Category {suffix}",
            normalized_name=f"category {suffix}",
            is_active=True,
        )
        session.add_all([unit, category])
        await session.flush()

        items = []
        for idx, (item_name, balance_qty) in enumerate(item_balances):
            item = Item(
                sku=f"SKU-{suffix}-{idx}",
                name=item_name,
                normalized_name=f"{item_name} {suffix} {idx}",
                category_id=category.id,
                unit_id=unit.id,
                is_active=True,
            )
            session.add(item)
            await session.flush()
            subject = InventorySubject(subject_type="catalog_item", item_id=item.id)
            session.add(subject)
            await session.flush()
            balance = Balance(
                site_id=site.id,
                inventory_subject_id=subject.id,
                item_id=item.id,
                qty=Decimal(balance_qty),
            )
            session.add(balance)
            items.append({
                "item_id": item.id,
                "item_name": item_name,
                "subject_id": subject.id,
                "balance_qty": balance_qty,
            })

        issue_object_id = None
        issue_object_name = None
        if include_issue_object:
            issue_cat = IssueObjectCategory(
                name=f"IO Cat {suffix}",
                normalized_key=f"io-cat-{suffix}",
            )
            session.add(issue_cat)
            await session.flush()
            issue_object = IssueObject(
                display_name=f"Иванов Иван {suffix}",
                object_type="person",
                normalized_key=f"io-{suffix}",
                category_id=issue_cat.id,
                is_active=True,
            )
            session.add(issue_object)
            await session.flush()
            issue_object_id = issue_object.id
            issue_object_name = issue_object.display_name
            first = items[0]
            issued = IssuedAssetBalance(
                issue_object_id=issue_object.id,
                inventory_subject_id=first["subject_id"],
                item_id=first["item_id"],
                qty=Decimal(issued_qty),
            )
            session.add(issued)

        await session.commit()

        result = {
            "site_id": site.id,
            "root_token": str(root.user_token),
            "observer_token": str(observer.user_token),
            "items": items,
            "issue_object_id": issue_object_id,
            "issue_object_name": issue_object_name,
        }
        if second_site and second_site_obj is not None:
            result["second_site_id"] = second_site_obj.id
        return result


async def _create_operation(
    client: AsyncClient,
    token: str,
    *,
    op_type: str,
    site_id: int,
    lines: list[dict],
    source_site_id: int | None = None,
    destination_site_id: int | None = None,
    issue_object_id: int | None = None,
) -> str:
    payload: dict = {"operation_type": op_type, "site_id": site_id, "lines": lines}
    if source_site_id is not None:
        payload["source_site_id"] = source_site_id
    if destination_site_id is not None:
        payload["destination_site_id"] = destination_site_id
    if issue_object_id is not None:
        payload["issue_object_id"] = issue_object_id
    resp = await client.post(
        "/api/v1/operations",
        json=payload,
        headers={"X-User-Token": token},
    )
    assert resp.status_code == 200, f"create failed: {resp.text}"
    return resp.json()["id"]


async def _submit(client: AsyncClient, token: str, op_id: str, *, expected_version: int | None = None):
    body: dict = {"submit": True}
    if expected_version is not None:
        body["expected_version"] = expected_version
    return await client.post(
        f"/api/v1/operations/{op_id}/submit",
        json=body,
        headers={"X-User-Token": token},
    )


def _line(item_id: int, qty: str | int, line_number: int) -> dict:
    return {"line_number": line_number, "item_id": item_id, "qty": qty}


@pytest.mark.asyncio
async def test_single_line_insufficient_returns_one_group(client, session_factory):
    seed = await _seed(session_factory, item_balances=[("Кабель ВВГ", "80.000")])
    item = seed["items"][0]
    op_id = await _create_operation(
        client, seed["root_token"], op_type="EXPENSE", site_id=seed["site_id"],
        lines=[_line(item["item_id"], 120, 1)],
    )

    resp = await _submit(client, seed["root_token"], op_id)
    assert resp.status_code == 409, resp.text
    data = resp.json()

    assert data["type"] == "urn:warehouse:problem:operation-submit-rejected"
    assert data["status"] == 409
    assert data["code"] == "operation_submit_rejected"
    errors = data["errors"]
    assert len(errors) == 1
    first = errors[0]
    assert first["code"] == "insufficient_stock"
    assert first["scope"] == "line_group"
    assert len(first["operation_line_ids"]) == 1
    assert first["item"]["id"] == item["item_id"]
    assert first["item"]["name"] == "Кабель ВВГ"
    assert first["stock_site"]["id"] == seed["site_id"]
    assert first["required_qty"] == "120.000"
    assert first["available_qty"] == "80.000"


@pytest.mark.asyncio
async def test_multiple_items_insufficient_returns_multiple_groups(client, session_factory):
    seed = await _seed(
        session_factory,
        item_balances=[("Item One", "30.000"), ("Item Two", "10.000")],
    )
    item_one = seed["items"][0]
    item_two = seed["items"][1]
    op_id = await _create_operation(
        client, seed["root_token"], op_type="EXPENSE", site_id=seed["site_id"],
        lines=[
            _line(item_one["item_id"], 60, 1),
            _line(item_two["item_id"], 40, 2),
        ],
    )

    resp = await _submit(client, seed["root_token"], op_id)
    assert resp.status_code == 409, resp.text
    errors = resp.json()["errors"]
    assert len(errors) == 2
    assert [e["item"]["id"] for e in errors] == [item_one["item_id"], item_two["item_id"]]
    assert errors[0]["required_qty"] == "60.000"
    assert errors[1]["required_qty"] == "40.000"


@pytest.mark.asyncio
async def test_two_lines_same_item_aggregate(client, session_factory):
    """TZ §5.2 scenario: 60 + 60 against an 80 balance → both lines reported."""
    seed = await _seed(
        session_factory,
        item_balances=[("Кабель ВВГ", "80.000")],
        second_site=True,
    )
    item = seed["items"][0]
    op_id = await _create_operation(
        client, seed["root_token"], op_type="MOVE",
        site_id=seed["site_id"],
        source_site_id=seed["site_id"],
        destination_site_id=seed["second_site_id"],
        lines=[
            _line(item["item_id"], 60, 1),
            _line(item["item_id"], 60, 2),
        ],
    )

    resp = await _submit(client, seed["root_token"], op_id)
    assert resp.status_code == 409, resp.text
    errors = resp.json()["errors"]
    assert len(errors) == 1
    first = errors[0]
    assert first["code"] == "insufficient_stock"
    assert len(first["operation_line_ids"]) == 2
    assert first["required_qty"] == "120.000"
    assert first["available_qty"] == "80.000"


@pytest.mark.asyncio
async def test_two_lines_same_item_one_alone_sufficient_aggregate(client, session_factory):
    """90 + 20 against an 80 balance → both lines reported (sum exceeds)."""
    seed = await _seed(
        session_factory,
        item_balances=[("Кабель ВВГ", "80.000")],
        second_site=True,
    )
    item = seed["items"][0]
    op_id = await _create_operation(
        client, seed["root_token"], op_type="MOVE",
        site_id=seed["site_id"],
        source_site_id=seed["site_id"],
        destination_site_id=seed["second_site_id"],
        lines=[
            _line(item["item_id"], 90, 1),
            _line(item["item_id"], 20, 2),
        ],
    )

    resp = await _submit(client, seed["root_token"], op_id)
    assert resp.status_code == 409, resp.text
    errors = resp.json()["errors"]
    assert len(errors) == 1
    first = errors[0]
    assert len(first["operation_line_ids"]) == 2
    assert first["required_qty"] == "110.000"
    assert first["available_qty"] == "80.000"


@pytest.mark.asyncio
async def test_adjustment_positive_does_not_trigger_check(client, session_factory):
    seed = await _seed(session_factory, item_balances=[("Item A", "0.000")])
    item = seed["items"][0]
    op_id = await _create_operation(
        client, seed["root_token"], op_type="ADJUSTMENT", site_id=seed["site_id"],
        lines=[_line(item["item_id"], 5, 1)],
    )

    resp = await _submit(client, seed["root_token"], op_id)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "submitted"


@pytest.mark.asyncio
async def test_decimal_precision_in_qty(client, session_factory):
    seed = await _seed(session_factory, item_balances=[("Item A", "80.000")])
    item = seed["items"][0]
    op_id = await _create_operation(
        client, seed["root_token"], op_type="EXPENSE", site_id=seed["site_id"],
        lines=[_line(item["item_id"], "120.000", 1)],
    )

    resp = await _submit(client, seed["root_token"], op_id)
    assert resp.status_code == 409, resp.text
    errors = resp.json()["errors"]
    assert errors[0]["required_qty"] == "120.000"
    assert errors[0]["available_qty"] == "80.000"


@pytest.mark.asyncio
async def test_stale_version_returns_envelope(client, session_factory):
    seed = await _seed(session_factory, item_balances=[("Item A", "200.000")])
    item = seed["items"][0]
    op_id = await _create_operation(
        client, seed["root_token"], op_type="EXPENSE", site_id=seed["site_id"],
        lines=[_line(item["item_id"], 10, 1)],
    )
    # Bump the version while staying in DRAFT (PATCH increments version).
    bump = await client.patch(
        f"/api/v1/operations/{op_id}",
        json={"notes": "version bump"},
        headers={"X-User-Token": seed["root_token"]},
    )
    assert bump.status_code == 200, bump.text

    resp = await _submit(client, seed["root_token"], op_id, expected_version=1)
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data["code"] == "operation_submit_rejected"
    errors = data["errors"]
    assert len(errors) == 1
    first = errors[0]
    assert first["code"] == "stale_version"
    assert first["scope"] == "operation"
    assert first["expected_version"] == 1
    assert first["actual_version"] == 2


@pytest.mark.asyncio
async def test_operation_in_wrong_state_returns_envelope(client, session_factory):
    seed = await _seed(session_factory, item_balances=[("Item A", "200.000")])
    item = seed["items"][0]
    op_id = await _create_operation(
        client, seed["root_token"], op_type="EXPENSE", site_id=seed["site_id"],
        lines=[_line(item["item_id"], 10, 1)],
    )
    cancel = await client.post(
        f"/api/v1/operations/{op_id}/cancel",
        json={"cancel": True},
        headers={"X-User-Token": seed["root_token"]},
    )
    assert cancel.status_code == 200, cancel.text

    resp = await _submit(client, seed["root_token"], op_id)
    assert resp.status_code == 409, resp.text
    errors = resp.json()["errors"]
    assert len(errors) == 1
    first = errors[0]
    assert first["code"] == "operation_in_wrong_state"
    assert first["scope"] == "operation"
    assert first["current_state"] == "cancelled"
    assert first["allowed_states"] == ["draft"]


@pytest.mark.asyncio
async def test_submit_after_submit_returns_operation_in_wrong_state(client, session_factory):
    """state-before-version: a re-submit yields wrong_state, not stale_version."""
    seed = await _seed(session_factory, item_balances=[("Item A", "200.000")])
    item = seed["items"][0]
    op_id = await _create_operation(
        client, seed["root_token"], op_type="EXPENSE", site_id=seed["site_id"],
        lines=[_line(item["item_id"], 10, 1)],
    )

    first = await _submit(client, seed["root_token"], op_id, expected_version=1)
    assert first.status_code == 200, first.text

    # The client still believes the version is 1, but the state check must
    # win over the version check.
    second = await _submit(client, seed["root_token"], op_id, expected_version=1)
    assert second.status_code == 409, second.text
    errors = second.json()["errors"]
    assert len(errors) == 1
    assert errors[0]["code"] == "operation_in_wrong_state"
    assert errors[0]["current_state"] == "submitted"


@pytest.mark.asyncio
async def test_submit_without_expected_version_still_checks_state(client, session_factory):
    seed = await _seed(session_factory, item_balances=[("Item A", "200.000")])
    item = seed["items"][0]
    op_id = await _create_operation(
        client, seed["root_token"], op_type="EXPENSE", site_id=seed["site_id"],
        lines=[_line(item["item_id"], 10, 1)],
    )

    first = await _submit(client, seed["root_token"], op_id)
    assert first.status_code == 200, first.text

    second = await _submit(client, seed["root_token"], op_id)
    assert second.status_code == 409, second.text
    assert second.json()["errors"][0]["code"] == "operation_in_wrong_state"


@pytest.mark.asyncio
async def test_submit_without_expected_version_skips_version_check_only(client, session_factory):
    seed = await _seed(session_factory, item_balances=[("Item A", "200.000")])
    item = seed["items"][0]
    op_id = await _create_operation(
        client, seed["root_token"], op_type="EXPENSE", site_id=seed["site_id"],
        lines=[_line(item["item_id"], 10, 1)],
    )
    # Bump version while staying in DRAFT.
    bump = await client.patch(
        f"/api/v1/operations/{op_id}",
        json={"notes": "version bump"},
        headers={"X-User-Token": seed["root_token"]},
    )
    assert bump.status_code == 200, bump.text

    resp = await _submit(client, seed["root_token"], op_id)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "submitted"


@pytest.mark.asyncio
async def test_issue_return_insufficient_issued_balance(client, session_factory):
    seed = await _seed(
        session_factory,
        item_balances=[("Шуруповёрт", "100.000")],
        include_issue_object=True,
        issued_qty="1.000",
    )
    item = seed["items"][0]
    op_id = await _create_operation(
        client, seed["root_token"], op_type="ISSUE_RETURN",
        site_id=seed["site_id"],
        issue_object_id=seed["issue_object_id"],
        lines=[_line(item["item_id"], 2, 1)],
    )

    resp = await _submit(client, seed["root_token"], op_id)
    assert resp.status_code == 409, resp.text
    errors = resp.json()["errors"]
    assert len(errors) == 1
    first = errors[0]
    assert first["code"] == "insufficient_issued_balance"
    assert first["scope"] == "line_group"
    assert first["item"]["id"] == item["item_id"]
    assert first["issue_object"]["id"] == seed["issue_object_id"]
    assert first["required_qty"] == "2.000"
    assert first["available_qty"] == "1.000"


@pytest.mark.asyncio
async def test_role_not_permitted_returns_403_envelope(client, session_factory):
    seed = await _seed(session_factory, item_balances=[("Item A", "200.000")])
    item = seed["items"][0]
    op_id = await _create_operation(
        client, seed["root_token"], op_type="EXPENSE", site_id=seed["site_id"],
        lines=[_line(item["item_id"], 10, 1)],
    )

    resp = await _submit(client, seed["observer_token"], op_id)
    assert resp.status_code == 403, resp.text
    data = resp.json()
    assert data["code"] == "operation_submit_rejected"
    errors = data["errors"]
    assert len(errors) == 1
    first = errors[0]
    assert first["code"] == "role_not_permitted"
    assert first["scope"] == "operation"
    assert set(first.keys()) == {"code", "scope"}


@pytest.mark.asyncio
async def test_operation_not_found_returns_404_envelope(client, session_factory):
    seed = await _seed(session_factory, item_balances=[("Item A", "200.000")])
    missing_id = str(uuid4())

    resp = await _submit(client, seed["root_token"], missing_id)
    assert resp.status_code == 404, resp.text
    data = resp.json()
    assert data["type"] == "urn:warehouse:problem:operation-not-found"
    assert data["code"] == "operation_not_found"
    assert data["status"] == 404
    errors = data["errors"]
    assert len(errors) == 1
    assert errors[0]["code"] == "operation_not_found"
    assert errors[0]["scope"] == "operation"


@pytest.mark.asyncio
async def test_legacy_detail_string_still_present_in_envelope(client, session_factory):
    seed = await _seed(session_factory, item_balances=[("Кабель ВВГ", "80.000")])
    item = seed["items"][0]
    op_id = await _create_operation(
        client, seed["root_token"], op_type="EXPENSE", site_id=seed["site_id"],
        lines=[_line(item["item_id"], 120, 1)],
    )

    resp = await _submit(client, seed["root_token"], op_id)
    assert resp.status_code == 409, resp.text
    data = resp.json()
    detail = data.get("detail")
    assert isinstance(detail, str)
    assert "Кабель ВВГ" in detail
    assert "Недостаточно товара" in detail


@pytest.mark.asyncio
async def test_deterministic_order_of_deficits(client, session_factory):
    """Groups are ordered by the first line's line_number, not by key order.

    Item B is seeded first (smaller subject id), but its line is second in
    the operation, so the group for item A must come first.
    """
    seed = await _seed(
        session_factory,
        item_balances=[("Item B", "0.000"), ("Item A", "80.000")],
        second_site=True,
    )
    item_b = seed["items"][0]
    item_a = seed["items"][1]
    op_id = await _create_operation(
        client, seed["root_token"], op_type="MOVE",
        site_id=seed["site_id"],
        source_site_id=seed["site_id"],
        destination_site_id=seed["second_site_id"],
        lines=[
            _line(item_a["item_id"], 60, 1),
            _line(item_b["item_id"], 40, 2),
            _line(item_a["item_id"], 60, 3),
        ],
    )

    resp = await _submit(client, seed["root_token"], op_id)
    assert resp.status_code == 409, resp.text
    errors = resp.json()["errors"]
    assert len(errors) == 2
    assert errors[0]["item"]["id"] == item_a["item_id"]
    assert errors[1]["item"]["id"] == item_b["item_id"]
    assert errors[0]["required_qty"] == "120.000"
    assert len(errors[0]["operation_line_ids"]) == 2


@pytest.mark.asyncio
async def test_get_for_update_called_once_per_unique_key(client, session_factory, monkeypatch):
    seed = await _seed(
        session_factory,
        item_balances=[("Item A", "80.000"), ("Item B", "80.000")],
    )
    item_a = seed["items"][0]
    item_b = seed["items"][1]
    op_id = await _create_operation(
        client, seed["root_token"], op_type="EXPENSE", site_id=seed["site_id"],
        lines=[
            _line(item_a["item_id"], 120, 1),
            _line(item_a["item_id"], 30, 2),
        ],
    )

    original = BalancesRepo.get_for_update
    calls: list[tuple[int, int]] = []

    async def counting(self, site_id: int, inventory_subject_id: int):
        calls.append((site_id, inventory_subject_id))
        return await original(self, site_id, inventory_subject_id)

    monkeypatch.setattr(BalancesRepo, "get_for_update", counting)

    resp = await _submit(client, seed["root_token"], op_id)
    assert resp.status_code == 409, resp.text
    assert len(calls) == 1, f"expected one lock per unique key, got {calls}"

    # Three lines over two unique keys → exactly two locks.
    op_id2 = await _create_operation(
        client, seed["root_token"], op_type="EXPENSE", site_id=seed["site_id"],
        lines=[
            _line(item_a["item_id"], 120, 1),
            _line(item_a["item_id"], 30, 2),
            _line(item_b["item_id"], 50, 3),
        ],
    )
    calls.clear()
    resp2 = await _submit(client, seed["root_token"], op_id2)
    assert resp2.status_code == 409, resp2.text
    assert len(calls) == 2, f"expected two locks for two keys, got {calls}"
    assert len({key for key in calls}) == 2
